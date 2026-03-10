# WealthPilot 서버 실행 가이드

## 사전 준비

- Node.js 18+
- Python 3.11+
- Docker Desktop (로컬 PostgreSQL용)

---

## 1. PostgreSQL 실행

Docker Desktop을 먼저 실행한 뒤:

```bash
cd /Users/jehoonyeon/workspace/side_project/WealthPilot
docker compose up -d
```

정상 확인:

```bash
docker ps
# wealthpilot_db 컨테이너가 healthy 상태인지 확인
```

접속 정보:
- Host: `localhost:5432`
- DB: `wealthpilot_dev`
- User: `postgres`
- Password: `postgres`

---

## 2. DB 마이그레이션

```bash
cd /Users/jehoonyeon/workspace/side_project/WealthPilot/backend
source .venv/bin/activate
alembic upgrade head
```

마이그레이션 상태 확인:

```bash
alembic current
```

새 마이그레이션 생성 (모델 변경 후):

```bash
alembic revision --autogenerate -m "변경 설명"
```

마이그레이션 롤백:

```bash
alembic downgrade -1
```

---

## 3. 백엔드 서버 실행

```bash
cd /Users/jehoonyeon/workspace/side_project/WealthPilot/backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger 문서: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

---

## 4. 프론트엔드 서버 실행

```bash
cd /Users/jehoonyeon/workspace/side_project/WealthPilot/frontend
npm run dev
```

- 화면: http://localhost:3000
- 접속하면 자동으로 `/dashboard`로 리다이렉트

---

## 5. 전체 실행 순서 요약

```
1. Docker Desktop 실행
2. docker compose up -d          # PostgreSQL
3. backend: source .venv/bin/activate && alembic upgrade head  # 마이그레이션
4. backend: uvicorn app.main:app --reload                      # API 서버
5. frontend: npm run dev                                       # 프론트 서버
6. 브라우저에서 http://localhost:3000 접속
```

---

## 환경변수 설정

최초 1회, `.env` 파일이 없으면 `.env.example`을 복사해서 생성:

```bash
# 백엔드
cp backend/.env.example backend/.env
# ENCRYPTION_KEY, JWT_SECRET 등 채우기

# 프론트엔드
cp frontend/.env.example frontend/.env.local
```

암호화 키 생성:

```bash
cd backend && source .venv/bin/activate
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 서버 종료

```bash
# 프론트/백엔드: 각 터미널에서 Ctrl+C
# PostgreSQL:
docker compose down
# 데이터 포함 삭제:
docker compose down -v
```
