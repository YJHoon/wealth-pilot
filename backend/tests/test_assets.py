"""자산 CRUD API 테스트"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.main import app
from app.models.asset import Asset, AssetStatus, AssetType, Currency
from app.models.user import User
from app.services.asset_service import asset_to_response

# --- 테스트 픽스처 ---

TEST_USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _make_test_user(user_id: uuid.UUID = TEST_USER_ID) -> User:
    user = MagicMock(spec=User)
    user.id = user_id
    user.email = "test@example.com"
    user.name = "Test User"
    user.totp_enabled = True
    return user


def _make_asset(
    user_id: uuid.UUID = TEST_USER_ID,
    asset_id: uuid.UUID | None = None,
    status: AssetStatus = AssetStatus.ACTIVE,
    quantity_enc: str = "enc_10",
    purchase_price_enc: str = "enc_50000",
    sold_price_enc: str | None = None,
    realized_pnl_enc: str | None = None,
    group_id: uuid.UUID | None = None,
    asset_type: AssetType = AssetType.DOMESTIC_STOCK,
) -> Asset:
    asset = MagicMock(spec=Asset)
    asset.id = asset_id or uuid.uuid4()
    asset.user_id = user_id
    asset.group_id = group_id
    asset.type = asset_type
    asset.status = status
    asset.name = "삼성전자"
    asset.ticker = "005930"
    asset.currency = Currency.KRW
    asset.quantity = quantity_enc
    asset.purchase_price = purchase_price_enc
    asset.current_price = Decimal("55000")
    asset.metadata_json = None
    asset.sold_at = None
    asset.sold_price = sold_price_enc
    asset.realized_pnl = realized_pnl_enc
    asset.created_at = datetime.now(timezone.utc)
    asset.updated_at = datetime.now(timezone.utc)
    return asset


# 의존성 오버라이드를 적용한 클라이언트
@pytest_asyncio.fixture
async def auth_client():
    """인증 우회 + DB mock이 적용된 테스트 클라이언트."""
    mock_db = AsyncMock()
    mock_user = _make_test_user()

    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            ac._mock_db = mock_db  # 테스트에서 DB mock 접근용
            ac._mock_user = mock_user
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client():
    """인증 없는 테스트 클라이언트 (의존성 오버라이드 없음)."""
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# --- 인증 테스트 ---


class TestAuthRequired:
    @pytest.mark.asyncio
    async def test_list_assets_without_token(self, unauth_client):
        """토큰 없이 자산 목록 요청 시 401."""
        resp = await unauth_client.get("/api/assets")
        assert resp.status_code == 403  # HTTPBearer returns 403 for missing token

    @pytest.mark.asyncio
    async def test_create_asset_without_token(self, unauth_client):
        """토큰 없이 자산 생성 요청 시 401."""
        resp = await unauth_client.post("/api/assets", json={})
        assert resp.status_code == 403


# --- 서비스 레이어 단위 테스트 ---


class TestAssetService:
    @pytest.mark.asyncio
    async def test_create_asset(self):
        """자산 생성 — 금액 필드 암호화 확인."""
        from app.schemas.asset import AssetCreateRequest
        from app.services.asset_service import create_asset

        db = AsyncMock()
        body = AssetCreateRequest(
            type=AssetType.DOMESTIC_STOCK,
            name="삼성전자",
            ticker="005930",
            currency=Currency.KRW,
            quantity=Decimal("10"),
            purchase_price=Decimal("50000"),
        )

        with patch("app.services.asset_service.encrypt_decimal") as mock_enc:
            mock_enc.side_effect = lambda v: f"encrypted_{v}"
            asset = await create_asset(db, TEST_USER_ID, body)

        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        added_asset = db.add.call_args[0][0]
        assert added_asset.quantity == "encrypted_10"
        assert added_asset.purchase_price == "encrypted_50000"
        assert added_asset.user_id == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_create_asset_with_group_verifies_ownership(self):
        """그룹 지정 시 소유권 검증."""
        from app.schemas.asset import AssetCreateRequest
        from app.services.asset_service import create_asset

        db = AsyncMock()
        group_id = uuid.uuid4()
        body = AssetCreateRequest(
            type=AssetType.CRYPTO,
            name="Bitcoin",
            currency=Currency.USD,
            quantity=Decimal("1"),
            purchase_price=Decimal("30000"),
            group_id=group_id,
        )

        # 그룹이 없는 경우 404
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with (
            patch("app.services.asset_service.encrypt_decimal"),
            pytest.raises(Exception) as exc_info,
        ):
            await create_asset(db, TEST_USER_ID, body)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_asset_not_found(self):
        """존재하지 않는 자산 조회 시 404."""
        from app.services.asset_service import get_asset_by_id

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        with pytest.raises(Exception) as exc_info:
            await get_asset_by_id(db, TEST_USER_ID, uuid.uuid4())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_asset_forbidden(self):
        """다른 사용자 자산 접근 시 403."""
        from app.services.asset_service import get_asset_by_id

        db = AsyncMock()
        asset = _make_asset(user_id=OTHER_USER_ID)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        db.execute.return_value = mock_result

        with pytest.raises(Exception) as exc_info:
            await get_asset_by_id(db, TEST_USER_ID, asset.id)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_sold_asset_rejected(self):
        """매도 자산 수정 시 400."""
        from app.schemas.asset import AssetUpdateRequest
        from app.services.asset_service import update_asset

        db = AsyncMock()
        asset = _make_asset(status=AssetStatus.SOLD)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        db.execute.return_value = mock_result

        body = AssetUpdateRequest(name="변경된 이름")

        with pytest.raises(Exception) as exc_info:
            await update_asset(db, TEST_USER_ID, asset.id, body)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_sold_asset_rejected(self):
        """매도 자산 삭제 시 400."""
        from app.services.asset_service import delete_asset

        db = AsyncMock()
        asset = _make_asset(status=AssetStatus.SOLD)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        db.execute.return_value = mock_result

        with pytest.raises(Exception) as exc_info:
            await delete_asset(db, TEST_USER_ID, asset.id)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_sell_asset_pnl_calculation(self):
        """매도 시 PnL 계산 정확성."""
        from app.schemas.asset import AssetSellRequest
        from app.services.asset_service import sell_asset

        db = AsyncMock()
        asset = _make_asset()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        db.execute.return_value = mock_result

        body = AssetSellRequest(sold_price=Decimal("60000"))

        with (
            patch("app.services.asset_service.decrypt_decimal") as mock_dec,
            patch("app.services.asset_service.encrypt_decimal") as mock_enc,
        ):
            mock_dec.side_effect = [Decimal("10"), Decimal("50000")]  # qty, buy_price
            encrypted_values = []
            mock_enc.side_effect = lambda v: (encrypted_values.append(v), f"enc_{v}")[1]

            result = await sell_asset(db, TEST_USER_ID, asset.id, body)

        # PnL = (60000 - 50000) * 10 = 100000
        assert Decimal("60000") in encrypted_values  # sold_price
        assert Decimal("100000") in encrypted_values  # realized_pnl
        assert asset.status == AssetStatus.SOLD

    @pytest.mark.asyncio
    async def test_sell_already_sold_asset_rejected(self):
        """이미 매도된 자산 재매도 시 400."""
        from app.schemas.asset import AssetSellRequest
        from app.services.asset_service import sell_asset

        db = AsyncMock()
        asset = _make_asset(status=AssetStatus.SOLD)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        db.execute.return_value = mock_result

        body = AssetSellRequest(sold_price=Decimal("60000"))

        with pytest.raises(Exception) as exc_info:
            await sell_asset(db, TEST_USER_ID, asset.id, body)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_update_encrypted_fields(self):
        """수정 시 금액 필드 재암호화."""
        from app.schemas.asset import AssetUpdateRequest
        from app.services.asset_service import update_asset

        db = AsyncMock()
        asset = _make_asset()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        db.execute.return_value = mock_result

        body = AssetUpdateRequest(quantity=Decimal("20"), purchase_price=Decimal("45000"))

        with patch("app.services.asset_service.encrypt_decimal") as mock_enc:
            mock_enc.side_effect = lambda v: f"enc_{v}"
            await update_asset(db, TEST_USER_ID, asset.id, body)

        # setattr로 암호화된 값이 설정되었는지 확인
        assert mock_enc.call_count == 2


class TestAssetToResponse:
    def test_decrypts_fields(self):
        """asset_to_response가 금액 필드를 올바르게 복호화."""
        asset = _make_asset()

        with (
            patch("app.services.asset_service.decrypt_decimal") as mock_dec,
            patch("app.services.asset_service.decrypt_decimal_optional") as mock_dec_opt,
        ):
            mock_dec.side_effect = [Decimal("10"), Decimal("50000")]
            mock_dec_opt.side_effect = [None, None]

            response = asset_to_response(asset)

        assert response.quantity == Decimal("10")
        assert response.purchase_price == Decimal("50000")
        assert response.sold_price is None
        assert response.realized_pnl is None


# --- 유효성 검증 테스트 ---


class TestAssetValidation:
    @pytest.mark.asyncio
    async def test_empty_name_rejected(self, auth_client):
        """빈 이름 → 422."""
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
            "name": "",
            "currency": "KRW",
            "quantity": "10",
            "purchase_price": "50000",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_quantity_rejected(self, auth_client):
        """음수 수량 → 422."""
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
            "name": "삼성전자",
            "currency": "KRW",
            "quantity": "-1",
            "purchase_price": "50000",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_zero_quantity_rejected(self, auth_client):
        """0 수량 → 422."""
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
            "name": "삼성전자",
            "currency": "KRW",
            "quantity": "0",
            "purchase_price": "50000",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_zero_sell_price_rejected(self, auth_client):
        """0원 매도가 → 422."""
        asset_id = uuid.uuid4()
        resp = await auth_client.post(f"/api/assets/{asset_id}/sell", json={
            "sold_price": "0",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, auth_client):
        """필수 필드 누락 → 422."""
        resp = await auth_client.post("/api/assets", json={
            "type": "domestic_stock",
        })
        assert resp.status_code == 422


# --- 암호화 확인 테스트 ---


class TestEncryption:
    @pytest.mark.asyncio
    async def test_quantity_stored_encrypted(self):
        """수량이 평문이 아닌 암호문으로 저장되는지 확인."""
        from app.schemas.asset import AssetCreateRequest
        from app.services.asset_service import create_asset

        db = AsyncMock()
        body = AssetCreateRequest(
            type=AssetType.DOMESTIC_STOCK,
            name="삼성전자",
            currency=Currency.KRW,
            quantity=Decimal("100"),
            purchase_price=Decimal("50000"),
        )

        with patch("app.services.asset_service.encrypt_decimal") as mock_enc:
            mock_enc.side_effect = lambda v: f"AES256_ENCRYPTED_{v}"
            await create_asset(db, TEST_USER_ID, body)

        added_asset = db.add.call_args[0][0]
        # DB에 저장되는 값이 평문("100")이 아님을 확인
        assert added_asset.quantity != "100"
        assert added_asset.quantity.startswith("AES256_ENCRYPTED_")
        assert added_asset.purchase_price != "50000"
        assert added_asset.purchase_price.startswith("AES256_ENCRYPTED_")
