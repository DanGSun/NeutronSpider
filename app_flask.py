from flask import Flask, jsonify
from core.rlib import get_engines
from core.spider import CrawlerRunner
import multiprocessing

app = Flask(__name__)
app.config.from_pyfile('fcfg.py')
crawler = CrawlerRunner()


@app.route("/spider/start")
def sp_strt():
        crawler.start()
        return jsonify({"status": crawler.running, "info": "started"})


@app.route("/spider/stop")
def sp_stop():
        crawler.stop()
        return jsonify({"status": crawler.running, "info": "stopped"})


@app.route("/spider/status")
def sp_status():
        return jsonify({"status": crawler.running, "info": crawler.get_info()})


@app.route("/spider/plugins")
def sp_plugins():
        return jsonify(get_engines())


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
