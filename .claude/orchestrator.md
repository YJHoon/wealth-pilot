# Orchestrator Workflow

## 실행 조건
사용자가 "agent workflow로 실행" 또는 "오케스트레이터 실행"을 명시한 경우에만 동작.

## Workflow

### Step 1: Worker 실행
`.claude/agents/worker.md` 지침으로 서브에이전트를 spawn한다.
전달 내용:
- 작업 설명
- 관련 파일 경로 (있을 경우)
- 리뷰어 피드백 (재작업 시)

### Step 2: diff 수집
git diff HEAD
git diff HEAD --stat

### Step 3: 테스트 실행
변경된 파일 경로 기준으로 판단:
- frontend/**  → cd frontend && npx tsc --noEmit && npm run lint
- backend/**   → cd backend && pytest -x -q --tb=short
- 양쪽 모두   → 둘 다 실행

### Step 4: 테스트 결과 판정
- 테스트 PASS → 사용자에게 완료 보고. PR 올리면 CodeRabbit이 리뷰.
- 테스트 FAIL → worker에게 실패 로그 전달 후 Step 1부터 반복
- 3회 반복 후에도 FAIL → 남은 이슈 목록과 함께 사용자에게 보고

### Step 5: 판정
- APPROVED → 사용자에게 완료 보고. git push 절대 하지 않음.
- ISSUES   → worker에게 피드백 전달 후 Step 1부터 반복
- 3회 반복 후에도 ISSUES → 남은 이슈 목록과 함께 사용자에게 보고

## 제약
- git push 금지 (항상)
- 최대 3 사이클
- 각 사이클에서 diff는 변경 파일만 reviewer에게 전달 (토큰 절약)
