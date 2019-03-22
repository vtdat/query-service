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

class Prom(Resource):
  def get(self):
    query = '(sum(node_memory_MemTotal_bytes{instance=~"node-exporter:9100"}) - sum(node_memory_MemFree_bytes{instance=~"node-exporter:9100"}+node_memory_Buffers_bytes{instance=~"node-exporter:9100"}+node_memory_Cached_bytes{instance=~"node-exporter:9100"}) ) / sum(node_memory_MemTotal_bytes{instance=~"node-exporter:9100"}) * 100'
    safe = '()_-&~*'
    start = '1553053590'
    end = '1553057220'
    step = '30'
    url = _HOST_ + ':' + _PROM_PORT_ + '/api/v1/query_range?query=' + urllib.parse.quote(query, safe=safe) + '&start=' + start + '&end=' + end + '&step=' + step
    r = requests.get(url)
    return jsonify(r.text)

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