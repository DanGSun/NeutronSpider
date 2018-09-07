# Create dummy secrey key so we can use sessions
SECRET_KEY = 'weknf383flask901ndscbd'

# Create in-memory database
DATABASE_FILE = 'db.sqlite'
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DATABASE_FILE
SQLALCHEMY_ECHO = True