"""한국투자증권 KIS Open API 클라이언트

인증(OAuth2), 시세 조회, 주문 실행, 잔고 조회를 담당.
계좌별로 인스턴스를 생성하여 사용한다.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from app.models.trading import TradingMode

logger = logging.getLogger(__name__)

# KIS API base URLs
_BASE_URLS = {
    TradingMode.LIVE: "https://openapi.koreainvestment.com:9443",
    TradingMode.PAPER: "https://openapivts.koreainvestment.com:29443",
}

# 모드별 Rate Limit (RPS)
_RATE_LIMITS = {
    TradingMode.LIVE: 20,
    TradingMode.PAPER: 5,
}

# 모의투자 tr_id 매핑 (실전 → 모의: T → V)
_PAPER_TR_PREFIX = "V"
_LIVE_TR_PREFIX = "T"


class KISClientError(Exception):
    """KIS API 호출 실패."""

    def __init__(self, message: str, status_code: int | None = None, response_data: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class KISClient:
    """한국투자증권 KIS Open API 클라이언트.

    계좌별로 인스턴스를 생성한다. 토큰 관리, rate limiting 내장.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_number: str,
        account_product_code: str = "01",
        mode: TradingMode = TradingMode.PAPER,
        access_token: str | None = None,
        token_expires_at: datetime | None = None,
    ):
        self._app_key = app_key
        self._app_secret = app_secret
        self._account_number = account_number
        self._account_product_code = account_product_code
        self._mode = mode
        self._access_token = access_token
        self._token_expires_at = token_expires_at

        self._base_url = _BASE_URLS[mode]
        self._semaphore = asyncio.Semaphore(_RATE_LIMITS[mode])
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

    async def close(self):
        await self._client.aclose()

    @property
    def mode(self) -> TradingMode:
        return self._mode

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def token_expires_at(self) -> datetime | None:
        return self._token_expires_at

    # ──────────────────────────────────────────
    # 인증
    # ──────────────────────────────────────────

    async def authenticate(self) -> str:
        """OAuth2 토큰 발급. 반환: access_token."""
        resp = await self._client.post(
            "/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        if resp.status_code != 200:
            raise KISClientError(
                f"KIS 토큰 발급 실패 (HTTP {resp.status_code})",
                status_code=resp.status_code,
                response_data=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {},
            )
        data = resp.json()

        self._access_token = data["access_token"]
        # KIS 토큰은 발급 후 약 24시간 유효
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        logger.info("KIS token obtained, expires_at=%s", self._token_expires_at)
        return self._access_token

    async def _ensure_token(self):
        """토큰이 없거나 만료 임박(5분 전)이면 재발급."""
        if self._access_token and self._token_expires_at:
            if datetime.now(timezone.utc) < self._token_expires_at - timedelta(minutes=5):
                return
        await self.authenticate()

    # ──────────────────────────────────────────
    # 공통 요청
    # ──────────────────────────────────────────

    def _tr_id(self, live_tr_id: str) -> str:
        """모의투자 모드면 tr_id 접두사를 V로 변환."""
        if self._mode == TradingMode.PAPER and live_tr_id.startswith(_LIVE_TR_PREFIX):
            return _PAPER_TR_PREFIX + live_tr_id[1:]
        return live_tr_id

    async def _request(
        self,
        method: str,
        path: str,
        *,
        tr_id: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        """KIS API 요청 — 인증 헤더, rate limit 포함."""
        await self._ensure_token()

        headers = {
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": self._tr_id(tr_id),
            "custtype": "P",
            "content-type": "application/json; charset=utf-8",
        }

        async with self._semaphore:
            if method.upper() == "GET":
                resp = await self._client.get(path, headers=headers, params=params)
            else:
                resp = await self._client.post(path, headers=headers, json=json_body)

        data = resp.json()

        # KIS 에러 체크
        rt_cd = data.get("rt_cd")
        if rt_cd and rt_cd != "0":
            msg = data.get("msg1", "Unknown KIS API error")
            logger.error("KIS API error: tr_id=%s, rt_cd=%s, msg=%s", tr_id, rt_cd, msg)
            raise KISClientError(msg, status_code=resp.status_code, response_data=data)

        return data

    # ──────────────────────────────────────────
    # 시세 조회
    # ──────────────────────────────────────────

    async def get_current_price(self, ticker: str) -> dict:
        """주식현재가 시세 조회 (FHKST01010100).

        Returns:
            {"price": Decimal, "name": str, "volume": int, "change_rate": Decimal, ...}
        """
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
            },
        )
        output = data.get("output", {})
        return {
            "price": Decimal(output.get("stck_prpr", "0")),
            "name": output.get("hts_kor_isnm", ""),
            "volume": int(output.get("acml_vol", "0")),
            "change_rate": Decimal(output.get("prdy_ctrt", "0")),
            "high": Decimal(output.get("stck_hgpr", "0")),
            "low": Decimal(output.get("stck_lwpr", "0")),
        }

    async def get_price_history(
        self, ticker: str, period: str = "D", count: int = 60,
    ) -> list[dict]:
        """주식현재가 일별 시세 조회 (FHKST01010400).

        Args:
            ticker: 종목코드 (6자리)
            period: D(일), W(주), M(월)
            count: 조회 일수 (최대 100)

        Returns:
            [{"date": str, "close": Decimal, "open": Decimal, "high": Decimal, "low": Decimal, "volume": int}, ...]
        """
        # 기간 설정: 오늘부터 count일 전
        end_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
        start_date = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=count * 2)).strftime("%Y%m%d")

        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            tr_id="FHKST01010400",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "0",
            },
        )

        results = []
        for item in data.get("output", []):
            if not item.get("stck_clpr"):
                continue
            results.append({
                "date": item.get("stck_bsop_date", ""),
                "close": Decimal(item["stck_clpr"]),
                "open": Decimal(item.get("stck_oprc", "0")),
                "high": Decimal(item.get("stck_hgpr", "0")),
                "low": Decimal(item.get("stck_lwpr", "0")),
                "volume": int(item.get("acml_vol", "0")),
            })

        # KIS는 최신순 → 오래된 순으로 정렬
        results.reverse()
        return results[-count:]

    # ──────────────────────────────────────────
    # 잔고 조회
    # ──────────────────────────────────────────

    async def get_balance(self) -> dict:
        """주식 잔고 조회 (TTTC8434R).

        Returns:
            {
                "cash": Decimal,
                "total_eval": Decimal,
                "total_pnl": Decimal,
                "holdings": [{"ticker": str, "name": str, "quantity": int, "avg_price": Decimal, ...}, ...]
            }
        """
        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id="TTTC8434R",
            params={
                "CANO": self._account_number,
                "ACNT_PRDT_CD": self._account_product_code,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )

        holdings = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty", "0"))
            if qty <= 0:
                continue
            holdings.append({
                "ticker": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "quantity": qty,
                "avg_price": Decimal(item.get("pchs_avg_pric", "0")),
                "current_price": Decimal(item.get("prpr", "0")),
                "eval_amount": Decimal(item.get("evlu_amt", "0")),
                "pnl": Decimal(item.get("evlu_pfls_amt", "0")),
                "pnl_rate": Decimal(item.get("evlu_pfls_rt", "0")),
            })

        output2 = data.get("output2", [{}])
        summary = output2[0] if output2 else {}
        return {
            "cash": Decimal(summary.get("dnca_tot_amt", "0")),
            "total_eval": Decimal(summary.get("scts_evlu_amt", "0")),
            "total_pnl": Decimal(summary.get("evlu_pfls_smtl_amt", "0")),
            "holdings": holdings,
        }

    # ──────────────────────────────────────────
    # 주문
    # ──────────────────────────────────────────

    async def place_order(
        self,
        side: str,
        ticker: str,
        quantity: int,
        price: int = 0,
        order_type: str = "market",
    ) -> dict:
        """주식 주문 (현금).

        Args:
            side: "buy" 또는 "sell"
            ticker: 종목코드
            quantity: 수량
            price: 지정가 (시장가 주문 시 0)
            order_type: "market" 또는 "limit"

        Returns:
            {"order_id": str, "order_date": str}
        """
        tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"

        # 주문 구분: 01=지정가, 05=시장가
        ord_dvsn = "05" if order_type == "market" else "01"

        data = await self._request(
            "POST",
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=tr_id,
            json_body={
                "CANO": self._account_number,
                "ACNT_PRDT_CD": self._account_product_code,
                "PDNO": ticker,
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": str(price),
            },
        )

        output = data.get("output", {})
        return {
            "order_id": output.get("ODNO", ""),
            "order_date": output.get("ORD_TMD", ""),
        }

    async def get_order_status(self, order_date: str | None = None) -> list[dict]:
        """당일 체결/미체결 조회 (TTTC8001R).

        Args:
            order_date: 조회일자 (YYYYMMDD). None이면 오늘.

        Returns:
            [{"order_id": str, "ticker": str, "side": str, "quantity": int,
              "filled_quantity": int, "price": Decimal, "status": str}, ...]
        """
        if order_date is None:
            order_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")

        data = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id="TTTC8001R",
            params={
                "CANO": self._account_number,
                "ACNT_PRDT_CD": self._account_product_code,
                "INQR_STRT_DT": order_date,
                "INQR_END_DT": order_date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "01",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )

        results = []
        for item in data.get("output1", []):
            total_qty = int(item.get("ord_qty", "0"))
            filled_qty = int(item.get("tot_ccld_qty", "0"))

            if filled_qty >= total_qty and total_qty > 0:
                status = "filled"
            elif filled_qty > 0:
                status = "partial"
            else:
                status = "submitted"

            side_code = item.get("sll_buy_dvsn_cd", "")
            side = "buy" if side_code == "02" else "sell"

            results.append({
                "order_id": item.get("odno", ""),
                "ticker": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "side": side,
                "quantity": total_qty,
                "filled_quantity": filled_qty,
                "price": Decimal(item.get("ord_unpr", "0")),
                "filled_price": Decimal(item.get("avg_prvs", "0")),
                "status": status,
            })

        return results

    async def cancel_order(self, order_id: str, order_date: str | None = None) -> dict:
        """주문 취소 (TTTC0803U).

        Args:
            order_id: KIS 주문번호 (ODNO)
            order_date: 주문일자. None이면 오늘.

        Returns:
            {"order_id": str, "result": str}
        """
        data = await self._request(
            "POST",
            "/uapi/domestic-stock/v1/trading/order-rvsecncl",
            tr_id="TTTC0803U",
            json_body={
                "CANO": self._account_number,
                "ACNT_PRDT_CD": self._account_product_code,
                "KRX_FWDG_ORD_ORGNO": "",
                "ORGN_ODNO": order_id,
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",  # 02=취소
                "ORD_QTY": "0",
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y",
            },
        )

        output = data.get("output", {})
        return {
            "order_id": output.get("ODNO", ""),
            "result": "cancelled",
        }
