# SECURITY.md — WealthPilot 보안 규칙

보안은 편의성보다 항상 우선한다.

## 암호화 필수 필드

다음 필드는 반드시 `crypto_service.py`의 AES-256으로 암복호화:

| 테이블 | 필드 |
|--------|------|
| assets | quantity, purchase_price, sold_price, realized_pnl |
| asset_snapshots | total_value_krw |
| transactions | amount |

## 인증 규칙

- Google OAuth + TOTP 2FA 필수 (2FA 미설정 시 강제 설정 유도)
- JWT Access Token: 15분 만료
- Refresh Token: 7일 만료
- 30분 미사용 시 자동 로그아웃
- 새 기기 로그인 시 텔레그램 알림

## 모든 API 필수 적용

- JWT 인증 미들웨어
- 사용자 소유권 검증 (본인 데이터만 접근 가능)
- 액세스 로그 기록 (로그인, 자산 변경 등)
- Rate Limiting:
  - 기본 API: 100 req/min per user
  - 로그인 엔드포인트: 10 req/min per user (강화된 제한)

## 절대 금지

- raw SQL 쿼리 (SQLAlchemy ORM만 사용)
- 환경변수 코드 하드코딩
- API 응답에 불필요한 민감 정보 포함
- 암호화 없이 금액 데이터 DB 저장

## API 실패 처리

- 시세 API 실패: 해당 부분만 빈칸 (마지막 캐시 + "오래됨" 라벨)
- 나머지 UI는 정상 동작 유지
- 에러 토스트로 사용자 안내
- Sentry 기록 + 텔레그램 알림