ARG PYTHON_VERSION=3.11.2-bullseye

FROM python:${PYTHON_VERSION} as python

FROM python as python-build-stage
ARG BUILD_ENVIRONMENT=requirements


RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    # psycopg dependencies to work with postgres
    libpq-dev 

COPY ./requirements.txt .

# Update pip before installing wheels
RUN pip install --upgrade pip && \
    pip wheel --wheel-dir /usr/src/app/wheels \
    -r ${BUILD_ENVIRONMENT}.txt


FROM python as python-run-stage
ARG BUILD_ENVIRONMENT=requirements

ARG APP_HOME=/app

# Image metadata
LABEL maintainer="tankoraphael@gmail.com"
LABEL description="Development Image for Media Index" 

# prevents python .pyc files to written to docker
ENV PYTHONDONTWRITEBYTECODE 1

# python output is transmitted directly to the terminal without being bufferred and allows 
# displays of application output in real time
ENV PYTHONUNBUFFERED 1

# Set a variable for workdir
ENV BUILD_ENV ${BUILD_ENVIRONMENT}

# set /app as workdir  
WORKDIR ${APP_HOME}


RUN apt-get update && apt-get install --no-install-recommends -y \
# psycopg dependencies to work with postgres
    libpq-dev \
    gettext \
# clean up unused file
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# copy wheels fron build stage stage 1 to stage 2
COPY --from=python-build-stage /usr/src/app/wheels /wheels/


RUN pip install --upgrade pip && \
    pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
    && rm -rf /wheels/

# entrypoint shell script
COPY ./docker/local/django/entrypoint /entrypoint

# process line endings of shell script by converting windows lines endings into unix lines endings
RUN sed -i 's/\r$//g' /entrypoint
# Make entry shell script executable
RUN chmod +x /entrypoint

# start shell script
COPY ./docker/local/django/start /start
RUN sed -i 's/\r$//g' /start
RUN chmod +x /start


COPY . ${APP_HOME}

# dir for entrypoint
ENTRYPOINT [ "/entrypoint" ]
