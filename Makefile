PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

.PHONY: setup backend frontend test typecheck

setup:
	cd backend && /opt/homebrew/bin/python3.12 -m venv .venv
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000 --loop asyncio

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/python -m pytest tests -q

typecheck:
	cd frontend && ./node_modules/.bin/tsc -b
