# pull official base image
FROM python:3.11.3-slim-buster

# set working directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# install odbc
# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    apt-transport-https \
    unixodbc \
    unixodbc-dev \
    odbcinst \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Add the Microsoft repository for the ODBC driver
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/10/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18
    
# install python dependencies
RUN apt-get update && pip install --upgrade pip
COPY ./requirements.txt ./requirements.txt
RUN pip install -r ./requirements.txt

# add app
COPY . .
EXPOSE 8000 80
CMD [ "python" , "main.py"]
