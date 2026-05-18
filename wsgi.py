import os

from viewr import create_app

config_name = os.environ.get("FLASK_CONFIG", "dev")
app = create_app(config_name)

if __name__ == "__main__":
    app.run(port=9000)
