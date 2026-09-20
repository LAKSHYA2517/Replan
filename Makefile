.PHONY: demo test bench replay check

check:
	@echo "Checking banned patterns..."
	@fail=0; \
	for pattern in "time\.time(" "time\.monotonic(" "datetime\.now(" "threading\." "multiprocessing\." "concurrent\.futures"; do \
		hits=$$(grep -rn "$$pattern" replan/ --include="*.py" 2>/dev/null | grep -v "replan/clock.py"); \
		if [ -n "$$hits" ]; then \
			echo "BANNED PATTERN '$$pattern':"; echo "$$hits"; fail=1; \
		fi; \
	done; \
	hits=$$(grep -rn "asyncio\.sleep(" replan/ --include="*.py" 2>/dev/null | grep -v "replan/clock.py"); \
	if [ -n "$$hits" ]; then \
		echo "BANNED PATTERN 'asyncio.sleep(' outside clock.py:"; echo "$$hits"; fail=1; \
	fi; \
	hits=$$(grep -rn "force=\|override=" replan/commit.py 2>/dev/null); \
	if [ -n "$$hits" ]; then \
		echo "BANNED: force=/override= on commit gate:"; echo "$$hits"; fail=1; \
	fi; \
	exit $$fail

test:
	pytest -q

bench:
	python -m bench.run

replay:
	python -m replan.replay

demo:
	python -m replan.runtime
