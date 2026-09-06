.PHONY: dev up stop migrate test seed demo openapi check-openapi serve
dev up stop migrate test seed demo openapi check-openapi serve:
	uv run --project backend python scripts/manage.py $@
