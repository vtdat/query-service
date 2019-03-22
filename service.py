from flask import Flask, request
from flask_restful import Resource, Api
from json import dumps
from flask import jsonify
import requests
import urllib
app = Flask(__name__)
api = Api(app)
_HOST_ = 'http://10.240.232.7'
_PROM_PORT_ = '9090'
_ES_PORT_ = '9200'

class PromQuery:
  safe_chars = '()_-&~*'
  
  memory = '(sum(node_memory_MemTotal_bytes{instance=~"node-exporter:9100"})' \
    '- sum(node_memory_MemFree_bytes{instance=~"node-exporter:9100"}' \
      '+node_memory_Buffers_bytes{instance=~"node-exporter:9100"}' \
        '+node_memory_Cached_bytes{instance=~"node-exporter:9100"}) )' \
          '/ sum(node_memory_MemTotal_bytes{instance=~"node-exporter:9100"}) * 100'
  
  cpu = '100 - (avg  (irate(node_cpu_seconds_total' \
    '{mode="idle",instance=~"node-exporter.*"}[1m])) * 100)'
  
  filesystem_usage = 'sum (container_fs_limit_bytes{instance=~"cadvisor:8080"}' \
    '- container_fs_usage_bytes{instance=~"cadvisor:8080"})' \
      '/ sum(container_fs_limit_bytes{instance=~"cadvisor:8080"})'

class Log(Resource):
  def get(self, spanid):
    query = '_all/_search?q=spanid:'
    url = _HOST_ + ':' + _ES_PORT_ + '/' + query + spanid
    r = requests.get(url)
    return jsonify(r.text)

class Trace(Resource):
  def get(self, spanid):
    return validate_trace(spanid)


def validate_trace(spanid):
  url = _HOST_ + ':' + _ES_PORT_ + '/_all/_validate/query?q=spanid:' + spanid
  r = requests.get(url)
  return jsonify(r.text)

api.add_resource(Prom, '/prom')
api.add_resource(Log, '/log/<spanid>')
api.add_resource(Trace, '/trace/<spanid>')

if __name__ == '__main__':
     app.run(port='5002')