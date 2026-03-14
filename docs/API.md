# WealthPilot API 명세

> 백엔드: FastAPI 0.1.0
> Base URL: `http://localhost:8000` (개발) / Railway 배포 URL (프로덕션)

---

## 1. 공통 사항

### 인증
- JWT Bearer Token (`Authorization: Bearer {access_token}`)
- Access Token: 15분 TTL
- Refresh Token: 7일 TTL (CAS 토큰 로테이션)

### JWT 페이로드

**Access Token**:
```json
{
  "sub": "user-uuid",
  "type": "access",
  "sid": "session-uuid",
  "totp_verified": true,
  "exp": 1710432896
}
```

**Refresh Token**:
```json
{
  "sub": "user-uuid",
  "type": "refresh",
  "totp_verified": true,
  "exp": 1711037696
}
```

### Rate Limiting
- 전역: **100 req/min** (인증 사용자는 user_id 기준, 비인증은 IP 기준)
- 로그인: **10 req/min**
- 초과 시 `429 Too Many Requests`

### 보안 헤더 (모든 응답)
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
```

### 에러 응답 형식
```json
{
  "detail": "한국어 에러 메시지"
}
```

### CORS
- `CORS_ORIGINS` 환경변수에 등록된 도메인만 허용
- Credentials 허용

---

## 2. 엔드포인트

### 헬스체크

#### `GET /health`

| 항목 | 값 |
|------|---|
| 인증 | 불필요 |
| Rate Limit | 전역 (100/min) |

**응답** `200`:
```json
{
  "status": "ok",
  "env": "development"
}
```

---

### 인증 (`/api/auth`)

#### `POST /api/auth/login`

Google OAuth 로그인. Google ID Token을 서버에서 검증 후 JWT 발급.

| 항목 | 값 |
|------|---|
| 인증 | 불필요 |
| Rate Limit | **10/min** |

**요청**:
```json
{
  "email": "user@example.com",
  "name": "사용자명",
  "google_id_token": "eyJ...",
  "device_info": "Mozilla/5.0..."  // 선택, 미입력 시 User-Agent 사용
}
```

**응답** `200`:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "totp_required": false,
  "totp_setup_required": true,
  "user": {
    "id": "550e8400-...",
    "email": "user@example.com",
    "name": "사용자명",
    "totp_enabled": false,
    "onboarding_completed": false,
    "created_at": "2026-03-14T00:00:00Z"
  }
}
```

**에러**:

| 코드 | 설명 |
|------|------|
| `401` | Google 토큰 검증 실패 / 이메일 없음 |
| `423` | 계정 잠금 (5회 실패 → 15분) |

**동작 상세**:
- 신규 사용자 자동 생성
- 2FA 사용자: `totp_verified=false` 토큰 발급 → `/2fa/verify` 필요
- 액세스 로그 기록 (`LOGIN` 또는 `LOGIN_CHALLENGE`)
- 비정상 접근 탐지 (새 기기, 빠른 반복 시도)

---

#### `POST /api/auth/refresh`

Refresh Token으로 새 Access Token + Refresh Token 발급 (토큰 로테이션).

| 항목 | 값 |
|------|---|
| 인증 | 불필요 (토큰은 Body로 전달) |
| Rate Limit | 전역 (100/min) |

**요청**:
```json
{
  "refresh_token": "eyJ..."
}
```

**응답** `200`:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**에러**:

| 코드 | 설명 |
|------|------|
| `401` | 토큰 만료 / 무효 / 이미 로테이션됨 |

**동작 상세**:
- CAS(compare-and-swap) 패턴으로 동시 요청 레이스 컨디션 방지
- `totp_verified` 클레임 유지 (2FA 우회 방지)
- 세션 `last_active_at`, `expires_at` 갱신

---

#### `GET /api/auth/me`

현재 로그인한 사용자 정보 조회.

| 항목 | 값 |
|------|---|
| 인증 | **필수** |
| Rate Limit | 전역 (100/min) |

**응답** `200`:
```json
{
  "id": "550e8400-...",
  "email": "user@example.com",
  "name": "사용자명",
  "totp_enabled": true,
  "onboarding_completed": false,
  "created_at": "2026-03-14T00:00:00Z"
}
```

---

### 2FA (`/api/auth/2fa`)

#### `POST /api/auth/2fa/setup`

2FA 설정 — TOTP 시크릿 생성 및 QR 코드 반환.

| 항목 | 값 |
|------|---|
| 인증 | **필수** |
| Rate Limit | 전역 (100/min) |

**응답** `200`:
```json
{
  "qr_code_base64": "iVBORw0KGgo...",
  "secret": "JBSWY3DPEBLW64TM...",
  "otpauth_uri": "otpauth://totp/WealthPilot:user@example.com?..."
}
```

**에러**:

| 코드 | 설명 |
|------|------|
| `403` | 2FA 재설정 시 현재 OTP 검증 미완료 |

**동작 상세**:
- 최초 설정: `totp_secret`에 암호화 저장 (아직 `totp_enabled=false`)
- 재설정: `pending_totp_secret`에 임시 저장 (기존 2FA 유지)

---

#### `POST /api/auth/2fa/verify`

2FA 코드 검증. 성공 시 `totp_verified=true` 토큰 재발급.

| 항목 | 값 |
|------|---|
| 인증 | **필수** |
| Rate Limit | 전역 (100/min) |

**요청**:
```json
{
  "code": "123456"
}
```

**응답 (성공)** `200`:
```json
{
  "verified": true,
  "message": "2FA 인증이 완료되었습니다.",
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

**응답 (실패)** `200`:
```json
{
  "verified": false,
  "message": "인증 코드가 올바르지 않습니다. 다시 확인해주세요.",
  "access_token": null,
  "refresh_token": null
}
```

**에러**:

| 코드 | 설명 |
|------|------|
| `400` | 2FA 미설정 상태 |
| `423` | 계정 잠금 (5회 실패 → 15분) |

**동작 상세**:
- 최초 설정 완료: `totp_enabled=true`
- 재설정 완료: `pending_totp_secret` → `totp_secret` 교체
- 실패 시 로그인 실패 카운터 증가 + 액세스 로그 기록
- 성공 시 실패 카운터 초기화 + Refresh Token 로테이션

---

### 세션 관리 (`/api/auth/sessions`)

#### `GET /api/auth/sessions`

활성 세션 목록 조회.

| 항목 | 값 |
|------|---|
| 인증 | **필수** |
| Rate Limit | 전역 (100/min) |

**응답** `200`:
```json
{
  "sessions": [
    {
      "id": "660e8400-...",
      "device_info": "Mozilla/5.0...",
      "ip_address": "203.0.113.45",
      "last_active_at": "2026-03-14T12:34:56Z",
      "created_at": "2026-03-14T10:00:00Z",
      "is_current": true
    }
  ],
  "total": 1
}
```

---

#### `DELETE /api/auth/sessions/{session_id}`

특정 세션 원격 종료 (본인 세션만).

| 항목 | 값 |
|------|---|
| 인증 | **필수** |
| Rate Limit | 전역 (100/min) |

**응답**: `204 No Content`

**에러**:

| 코드 | 설명 |
|------|------|
| `404` | 세션 없음 또는 본인 소유 아님 |

---

#### `POST /api/auth/logout`

현재 세션 로그아웃. JWT의 `sid`로 해당 세션만 삭제.

| 항목 | 값 |
|------|---|
| 인증 | **필수** |
| Rate Limit | 전역 (100/min) |

**응답**: `204 No Content`

---

### 자산 관리 (`/api/assets`)

모든 엔드포인트: `get_current_active_user` (JWT + 2FA 검증 필수)

#### `GET /api/assets`

사용자의 자산 목록 조회. 쿼리 파라미터로 필터링 가능.

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |

**쿼리 파라미터**:

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `type` | AssetType | `cash`, `domestic_stock`, `foreign_stock`, `crypto`, `real_estate` |
| `status_filter` | AssetStatus | `active`, `sold`, `delisted` |
| `group_id` | UUID | 포트폴리오 그룹 ID |

**응답** `200`:
```json
{
  "assets": [
    {
      "id": "550e8400-...",
      "user_id": "660e8400-...",
      "group_id": null,
      "type": "domestic_stock",
      "status": "active",
      "name": "삼성전자",
      "ticker": "005930",
      "currency": "KRW",
      "quantity": "10",
      "purchase_price": "70000",
      "current_price": "75000",
      "metadata_json": null,
      "sold_at": null,
      "sold_price": null,
      "realized_pnl": null,
      "created_at": "2026-03-14T00:00:00Z",
      "updated_at": "2026-03-14T00:00:00Z"
    }
  ],
  "total": 1
}
```

---

#### `POST /api/assets`

새 자산 등록. 금액 필드(quantity, purchase_price)는 서버에서 AES-256 암호화 후 DB 저장.

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |
| 감사 로그 | `ASSET_CREATE` |

**요청**:
```json
{
  "type": "domestic_stock",
  "name": "삼성전자",
  "ticker": "005930",
  "currency": "KRW",
  "quantity": "10",
  "purchase_price": "70000",
  "current_price": "75000",
  "group_id": "550e8400-...",
  "metadata_json": {"sector": "반도체"}
}
```

**응답** `201`: `AssetResponse` (위 목록 응답의 단일 객체)

**에러**:

| 코드 | 설명 |
|------|------|
| `404` | 존재하지 않는 그룹 ID |
| `422` | 필수 필드 누락, quantity ≤ 0 |

---

#### `PUT /api/assets/{id}`

자산 정보 수정 (부분 업데이트). `exclude_unset=True`로 전달된 필드만 변경.

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |
| 감사 로그 | `ASSET_UPDATE` |

**요청** (변경할 필드만):
```json
{
  "name": "삼성전자 우선주",
  "quantity": "20"
}
```

**응답** `200`: `AssetResponse`

**에러**:

| 코드 | 설명 |
|------|------|
| `403` | 매도된 자산은 수정 불가 |
| `404` | 자산 없음 또는 본인 소유 아님 |

---

#### `DELETE /api/assets/{id}`

자산 삭제 (하드 삭제).

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |
| 감사 로그 | `ASSET_DELETE` |

**응답**: `204 No Content`

**에러**:

| 코드 | 설명 |
|------|------|
| `403` | 매도된 자산은 삭제 불가 |
| `404` | 자산 없음 또는 본인 소유 아님 |

---

#### `POST /api/assets/{id}/sell`

자산 매도 처리 (단일 트랜잭션, 원자적).

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |
| 감사 로그 | `ASSET_SELL` |

**요청**:
```json
{
  "sold_price": "80000"
}
```

**응답** `200`: `AssetResponse` (status=sold, realized_pnl 포함)

**에러**:

| 코드 | 설명 |
|------|------|
| `403` | 이미 매도된 자산 |
| `404` | 자산 없음 또는 본인 소유 아님 |

**동작 상세**:
1. `status=SOLD`, `sold_at=now(UTC)`, `sold_price` 암호화 저장
2. `realized_pnl = (sold_price - purchase_price) * quantity` 계산 후 암호화 저장
3. 총 매도대금(`sold_price * quantity`)을 같은 통화의 활성 현금 자산에 합산 (없으면 "매도 수익금" 이름으로 생성)
4. 단일 `commit`으로 원자성 보장

---

### 포트폴리오 그룹 (`/api/groups`)

모든 엔드포인트: `get_current_active_user` (JWT + 2FA 검증 필수)

#### `GET /api/groups`

사용자의 포트폴리오 그룹 목록 조회. `asset_count`는 서브쿼리로 계산.

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |

**응답** `200`:
```json
{
  "groups": [
    {
      "id": "550e8400-...",
      "name": "국내주식",
      "description": "국내 상장 주식",
      "sort_order": 0,
      "created_at": "2026-03-14T00:00:00Z",
      "asset_count": 5
    }
  ],
  "total": 1
}
```

---

#### `POST /api/groups`

새 포트폴리오 그룹 생성.

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |

**요청**:
```json
{
  "name": "국내주식",
  "description": "국내 상장 주식",
  "sort_order": 0
}
```

**응답** `201`: `GroupResponse` (asset_count=0)

**에러**:

| 코드 | 설명 |
|------|------|
| `422` | name 누락 또는 100자 초과 |

---

#### `PUT /api/groups/{id}`

그룹 수정 (부분 업데이트).

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |

**응답** `200`: `GroupResponse`

**에러**:

| 코드 | 설명 |
|------|------|
| `404` | 그룹 없음 또는 본인 소유 아님 |

---

#### `DELETE /api/groups/{id}`

그룹 삭제. 소속 자산의 `group_id`는 `null`로 업데이트.

| 항목 | 값 |
|------|---|
| 인증 | **필수** (2FA 포함) |
| Rate Limit | 전역 (100/min) |

**응답**: `204 No Content`

**에러**:

| 코드 | 설명 |
|------|------|
| `404` | 그룹 없음 또는 본인 소유 아님 |

---

## 3. 미구현 엔드포인트 (TODO)

### 대시보드 (`/api/dashboard`)

```
GET    /api/dashboard/summary      # 자산 요약 (총액, 비중, 손익)
GET    /api/dashboard/history      # 자산 변동 추이 (?period=1M|3M|6M|1Y)
POST   /api/dashboard/snapshot     # 자산 스냅샷 저장
```

### 시세 (`/api/prices`)

```
GET    /api/prices/stock/{ticker}      # 주식 현재가
GET    /api/prices/crypto/{symbol}     # 코인 현재가
GET    /api/prices/exchange-rate       # 환율 (?from=USD&to=KRW)
POST   /api/prices/refresh             # 시세 일괄 갱신
GET    /api/prices/mode                # 시세 모드 조회
PUT    /api/prices/mode                # 시세 모드 변경
```

### 보안 (`/api/security`)

```
GET    /api/security/access-logs       # 액세스 로그 조회
```

---

## 4. 인증 의존성

### `get_current_user`
- JWT Access Token 검증
- `sub`에서 user_id 추출 → DB 조회
- Rate Limit에 user_id 설정
- 실패 시 `401 Unauthorized`

### `get_current_active_user`
- `get_current_user` + 2FA 검증 확인
- `totp_enabled=true`인 경우 `totp_verified=true` 필수
- 실패 시 `403 Forbidden`

---

## 5. Swagger 문서

개발 환경에서만 접근 가능:
- **Swagger UI**: `http://localhost:8000/docs`
- 프로덕션(`ENV=production`)에서는 비활성화
