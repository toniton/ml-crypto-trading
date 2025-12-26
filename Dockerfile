FROM python:3.12
LABEL authors="toni"

COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "main.py"]