Create a new user and setup a password, don't use the default ones.
Or you can do this with the docker when you hosting the application

#### Windows ->

````postgresql
psql -U postgres -c "CREATE USER <username> WITH PASSSWORD <'password';>"
createdb -U postgres -O <username> <dbname>
psql <dbname> -U <username>
\dt
\d users
````

okay you need to setup alembic, and how to do it?

1. install it.

````text
uv add alembic
````

2. run `uv run alembic init -t async alembic` this t means template async
   means use async template and the last alembic means the folder name

````text
uv run alembic init -t async alembic
````

3. edit `alembic.ini` and `alembic/env.py` to match your database settings
   remove hardcode database url from alembic.ini and setup
   config.set_main_option ("sqlalchemy.url", settings.database_url)
   target_metadata = Base.metadata
   inside the env.py file, import models from app.models.models

4. create a new migration file with `uv run alembic revision --autogenerate -m "initial migration"`
5. run the migration with `uv run alembic upgrade head`
6. check current version with `uv run alembic current`

Note ->
if you are using any special characters in your database url,
you need first render URL as a properly escaped string,
then double-escape % for ConfigParser interpolation

````text
# Render the URL as a properly escaped string
stringified_sqlalchemy_url = settings.database_url.render_as_string(
    hide_password=False
)

# Double-escape % for ConfigParser interpolation
percent_replaced_url = stringified_sqlalchemy_url.replace("%", "%%")

# Now set it
config.set_main_option("sqlalchemy.url", percent_replaced_url)
````

