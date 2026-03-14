# WealthPilot 배포 가이드

---

## 1. 로컬 개발 환경

### 사전 요구사항
- Node.js 18+
- Python 3.11+
- Docker Desktop
- Git

### 1-1. PostgreSQL 실행

```bash
# Docker Desktop 실행 후
docker compose up -d

# 상태 확인
docker ps
# wealthpilot_db 컨테이너가 healthy 상태인지 확인
```

접속 정보:
- Host: `localhost:5432`
- DB: `wealthpilot_dev`
- User/Password: `postgres/postgres`

### 1-2. 백엔드 설정

```bash
cd backend

# 가상환경 생성 (최초 1회)
python3 -m venv .venv

# 가상환경 활성화
source .venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 테스트용

# 환경변수 설정 (최초 1회)
cp .env.example .env
# .env 파일에서 ENCRYPTION_KEY, JWT_SECRET 등 채우기

# DB 마이그레이션
alembic upgrade head
```

**암호화 키 생성**:
```bash
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

### 1-3. 프론트엔드 설정

```bash
cd frontend

# 패키지 설치
npm install

# 환경변수 설정 (최초 1회)
cp .env.example .env.local
# .env.local에서 NEXTAUTH_SECRET, Google OAuth 키 등 채우기
```

### 1-4. 개발 서버 실행

```bash
# 터미널 1: 백엔드
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload
# → http://localhost:8000 (API)
# → http://localhost:8000/docs (Swagger)

# 터미널 2: 프론트엔드
cd frontend && npm run dev
# → http://localhost:3000
```

### 1-5. 서버 종료

```bash
# 프론트/백엔드: 각 터미널에서 Ctrl+C
# PostgreSQL:
docker compose down
# 데이터 포함 삭제:
docker compose down -v
```

---

## 2. 환경변수 레퍼런스

### 백엔드 (`backend/.env`)

| 변수 | 설명 | 필수 | 기본값 |
|------|------|------|--------|
| `DATABASE_URL` | PostgreSQL 연결 문자열 (asyncpg) | ✅ | `postgresql+asyncpg://postgres:postgres@localhost:5432/wealthpilot_dev` |
| `ENCRYPTION_KEY` | AES-256 암호화 키 (32바이트 base64) | ✅ | - |
| `JWT_SECRET` | JWT 서명 키 | ✅ | - |
| `JWT_ALGORITHM` | JWT 알고리즘 | - | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token TTL (분) | - | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token TTL (일) | - | `7` |
| `NEXTAUTH_SECRET` | NextAuth 공유 시크릿 | ✅ | - |
| `CORS_ORIGINS` | 허용 도메인 (쉼표 구분) | ✅ | `http://localhost:3000` |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | ✅ | - |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 클라이언트 시크릿 | ✅ | - |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 | - | - |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID | - | - |
| `SENTRY_DSN` | Sentry DSN | - | - |
| `ENV` | 환경 (`development` / `production`) | - | `development` |

### 프론트엔드 (`frontend/.env.local`)

| 변수 | 설명 | 필수 | 기본값 |
|------|------|------|--------|
| `NEXT_PUBLIC_API_URL` | 백엔드 API URL | ✅ | `http://localhost:8000` |
| `NEXTAUTH_URL` | NextAuth 콜백 URL | ✅ | `http://localhost:3000` |
| `NEXTAUTH_SECRET` | NextAuth 시크릿 (백엔드와 동일) | ✅ | - |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | ✅ | - |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 클라이언트 시크릿 | ✅ | - |
| `NEXT_PUBLIC_SENTRY_DSN` | Sentry DSN (프론트) | - | - |

---

## 3. 프로덕션 배포

### 3-1. 프론트엔드 → Vercel

> TODO: `vercel.json` 설정 파일 미생성

**배포 절차**:
1. Vercel에 GitHub 레포 연결
2. Root Directory: `frontend`
3. Framework Preset: Next.js
4. 환경변수 설정:
   - `NEXT_PUBLIC_API_URL`: Railway 백엔드 URL
   - `NEXTAUTH_URL`: `https://{app-name}.vercel.app`
   - `NEXTAUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
5. 빌드 확인: `npm run build` 에러 없는지

**next.config.mjs 주요 설정**:
- API 프록시: `/api/backend/:path*` → `NEXT_PUBLIC_API_URL`로 리라이트
- 보안 헤더: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- PWA: `@ducanh2912/next-pwa` (프로덕션에서만 활성)

### 3-2. 백엔드 → Railway

> TODO: `railway.json` 또는 `railway.toml` 설정 파일 미생성

**배포 절차**:
1. Railway에 GitHub 레포 연결
2. Root Directory: `backend`
3. Dockerfile 사용 (`backend/Dockerfile`)
4. 환경변수 설정:
   - `DATABASE_URL`: Railway PostgreSQL 또는 외부 DB URL
   - `ENCRYPTION_KEY`, `JWT_SECRET`, `NEXTAUTH_SECRET`
   - `CORS_ORIGINS`: Vercel 도메인 (`https://{app-name}.vercel.app`)
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `ENV`: `production`
   - 선택: `SENTRY_DSN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
5. Health Check: `GET /health`

**Dockerfile 요약**:
- Base: `python:3.11-slim`
- 비루트 사용자(`appuser`)로 실행
- Port: 8000
- CMD: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 3-3. 데이터베이스

> TODO: 프로덕션 DB 미구성

**옵션**:
- **Supabase** (무료 티어): PostgreSQL + 관리 UI
- **Neon** (무료 티어): 서버리스 PostgreSQL
- **Railway PostgreSQL**: Railway 내장 플러그인

**주의사항**:
- SSL 연결 필수
- `DATABASE_URL`에 `?sslmode=require` 추가
- asyncpg 드라이버 사용: `postgresql+asyncpg://...`
- 무료 DB 용량 (500MB) 관리를 위해 데이터 보관 정책 적용 필요

---

## 4. DB 마이그레이션 (Alembic)

```bash
cd backend && source .venv/bin/activate

# 마이그레이션 적용
alembic upgrade head

# 현재 상태 확인
alembic current

# 새 마이그레이션 생성 (모델 변경 후)
alembic revision --autogenerate -m "변경 설명"

# 롤백 (1단계)
alembic downgrade -1
```

**현재 마이그레이션 히스토리**:
1. `create_initial_tables` — 초기 테이블 생성
2. `add_login_failure_fields` — 로그인 실패 추적 필드
3. `add_refresh_token_hash_to_sessions` — 세션 토큰 해시
4. `security_fixes_v3` — 보안 수정

---

## 5. Docker

### 로컬 PostgreSQL (`docker-compose.yml`)

```yaml
# PostgreSQL 15 Alpine
# Port: 5432
# DB: wealthpilot_dev
# 볼륨: postgres_data (영구 저장)
```

```bash
docker compose up -d      # 시작
docker compose down        # 중지
docker compose down -v     # 중지 + 데이터 삭제
```

### 백엔드 컨테이너 빌드 (선택)

```bash
cd backend
docker build -t wealthpilot-api .
docker run -p 8000:8000 --env-file .env wealthpilot-api
```

---

## 6. 모니터링

### Sentry
- 백엔드: `sentry-sdk[fastapi]` — `SENTRY_DSN` 환경변수 설정 시 자동 활성화
- Traces Sample Rate: 10%
- 프로덕션에서만 사용 권장

### 텔레그램 알림
- `alert_service.py`를 통한 보안 알림
- 설정: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
- 알림 대상: 새 기기 로그인, 빠른 반복 로그인 시도, 비정상 접근

---

## 7. CI/CD

> TODO: GitHub Actions 워크플로우 미구성

**계획**:
- `develop` 브랜치 push 시 테스트 자동 실행
- `main` 브랜치 push 시 프로덕션 배포
- 린트 + 타입체크 + pytest + 빌드 검증

---

## 8. 유용한 명령어

```bash
# 프론트엔드
cd frontend && npm run dev          # 개발 서버
cd frontend && npm run build        # 프로덕션 빌드
cd frontend && npm run lint         # ESLint
cd frontend && npx tsc --noEmit     # 타입체크

# 백엔드
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload       # 개발 서버
pytest -x -q --tb=short             # 테스트
pytest --cov=app                    # 커버리지
alembic upgrade head                # 마이그레이션 적용

# Docker
docker compose up -d                # PostgreSQL 시작
docker compose down                 # PostgreSQL 중지
docker compose logs postgres        # 로그 확인
```
