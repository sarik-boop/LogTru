FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
WORKDIR /robot
RUN pip install --no-cache-dir httpx==0.27.2
COPY . .
CMD ["python", "quickmanage.py"]
