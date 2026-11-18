FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
WORKDIR /robot
RUN pip install --no-cache-dir httpx==0.27.2 playwright==1.47.0
COPY . .
CMD ["python3", "quickmanage.py"]
