FROM python:3.8.2
WORKDIR /app
COPY . /app
RUN pip install -Ur requirements.txt
ENTRYPOINT ["python3", "-m",  "dozer"]
