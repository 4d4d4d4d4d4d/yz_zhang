PY ?= python3
export PYTHONPATH := src:.

.PHONY: gate test lint fmt demo iterate hooks

gate:      ## 入库门禁（全部）
	$(PY) harness/gate.py
test:
	$(PY) -m unittest discover -s tests -t . -v
lint:
	ruff check . && ruff format --check .
fmt:
	ruff check --fix . && ruff format .
demo:
	$(PY) -m signalnet demo
iterate:   ## 跑门禁并刷新 TODO.md 自动区
	$(PY) harness/iterate.py
hooks:     ## 安装 git pre-commit 门禁
	git config core.hooksPath .githooks
