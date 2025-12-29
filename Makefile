VENV_DIR := ./venv
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
PYLINT := $(VENV_DIR)/bin/pylint

.PHONY: clean

venv: $(VENV_DIR)/bin/activate

$(VENV_DIR)/bin/activate: requirements.txt requirements-dev.txt
	python3 -m venv $(VENV_DIR)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	touch $(VENV_DIR)/bin/activate

pre-build:
	mkdir $(VENV_DIR)/bin && mkdir $(PYTHON) && mkdir $(PIP)

clean:
	rm -rf $(VENV_DIR)

migrate:
	alembic revision --autogenerate -m "Updated order table"

upgrade:
	alembic upgrade head

format:
	pre-commit

lint: .pylintrc
	$(PYLINT) src tests database main.py --rcfile=.pylintrc --fail-on=E,unused-import --fail-under=9.7

test:
	export PYTHONPATH=$$PYTHONPATH:. && $(VENV_DIR)/bin/pytest tests/ --cov --cov-branch --cov-report=xml

start:
	$(PYTHON) ./main.py