from flask import Flask, jsonify, request
from flask_restful import Resource, Api
from requests.auth import HTTPBasicAuth
import datetime
import json
import urllib
import requests

app = Flask(__name__)
api = Api(app)
HOST = 'http://10.240.201.100'
METRICS_IP = '10.240.202.111' # TRACKED HOST IP
PROM_PORT = '9091'
ES_PORT = '9200'

"""
Define Prometheus query.
"""

class PromQuery:
  safe_chars = '()_-&~*'
  time_gap = 600
  step = '10'

  memory = '(sum(node_memory_MemTotal_bytes{{instance=~"{0}:9100"}})' \
    '- sum(node_memory_MemFree_bytes{{instance=~"{0}:9100"}}' \
      '+node_memory_Buffers_bytes{{instance=~"{0}:9100"}}' \
        '+node_memory_Cached_bytes{{instance=~"{0}:9100"}}) )' \
          '/ sum(node_memory_MemTotal_bytes{{instance=~"{0}:9100"}}) * 100' . format(METRICS_IP)

  cpu = '100 - (avg  (irate(node_cpu_seconds_total' \
    '{{mode="idle",instance=~"{0}.*"}}[1m])) * 100)' . format(METRICS_IP)
  
  filesystem_usage = 'sum (container_fs_limit_bytes{{instance=~"{0}:8080"}}' \
    '- container_fs_usage_bytes{{instance=~"{0}:8080"}})' \
      '/ sum(container_fs_limit_bytes{{instance=~"{0}:8080"}})' . format(METRICS_IP)

"""
Getting logs from ElasticSearch.
Might not need this if changing to use JaegerUI.
@params: 
  - spanid: identifier of span
@return:
  - error: 0/1
  - message: description
  - data: logs data
"""
class Logs(Resource):
  def get(self, spanid):
    span_info = json.loads(get_span_time(spanid))
    if span_info['error'] == 0:
      # convert millisecond epoch timestamp to human date
      time = datetime.datetime.fromtimestamp(span_info['data']['start_time']/1000).date() 
      try:
        query = 'vsmart-'+ time.strftime('%Y.%m.%d') \
          + '/_search?q=spanid:'
        # request url
        url = HOST + ':' + ES_PORT + '/' + query + spanid
        r = json.loads(requests.get(url).text)
        if r['hits']['total'] > 0:
          return jsonify({
            'error' : 0,
            'data' : [i['_source'] for i in r['hits']['hits']],
            'message' : 'Records retrieved'
          })
        return jsonify({
          'error' : 0,
          'message' : 'No record found'
        })
      except:
        return jsonify({
          'error' : 1,
          'message' : 'There was an error'
        })
    return jsonify({
      'error' : 1,
      'message' : span_info['message']
    })

"""
Getting logs from ElasticSearch.
Might not need this if changing to use JaegerUI.
@params: 
  - spanid: identifier of span
@return:
  - error: 0/1
  - message: description
  - data: metrics data
"""
class Prom(Resource):
  def get(self, spanid):
    span_info = json.loads(get_span_time(spanid))
    if span_info['error'] == 0:
      try:
        # convert millisecond epoch start_time, end_time timestamp
        # to second epoch timestamp
        start_time = int(span_info['data']['start_time']/1000)
        end_time = int(span_info['data']['end_time']/1000)
        # request url
        url = HOST + ':' + PROM_PORT + '/api/v1/query_range?query=' \
          + urllib.parse.quote(PromQuery.memory, safe=PromQuery.safe_chars) \
            + '&start=' + str(start_time - PromQuery.time_gap) \
              + '&end=' + str(end_time + PromQuery.time_gap) + '&step=' + PromQuery.step
        # authentication is optional
        r = json.loads(requests.get(url, auth=HTTPBasicAuth('prom_user', 'prom_password')).text)
        if r['status'] == 'success':
          return jsonify({
            'error' : 0,
            'data' : r['data']['result'][0]['values'],
            'message' : 'Records retrieved'
          })
        return jsonify({
          'error' : 0,
          'message' : 'No record found'
        })
      except:
        return jsonify({
          'error' : 1,
          'message' : 'There was an error'
        })
    return jsonify({
      'error' : 1,
      'message' : span_info['message']
    })

"""
Get Span start_time and end_time from spanid
"""
def get_span_time(spanid):
  url = HOST + ':' + ES_PORT + '/jaeger-*/_search?q=spanID:' + spanid
  try:
    r = json.loads(requests.get(url).text)
    if r['hits']['total'] > 0:
      return json.dumps({
        'error' : 0,
        'message' : 'OK',
        'data' : {
          'start_time' : r['hits']['hits'][0]['_source']['startTimeMillis'],
          'end_time' :  r['hits']['hits'][0]['_source']['startTimeMillis'] \
            + r['hits']['hits'][0]['_source']['duration']
        }
      })
    return json.dumps({
      'error' : 1,
      'message' : 'Span not found'
    })
  except:
    return json.dumps({
      'error' : 1,
      'message' : 'There was an error'
    })

api.add_resource(Logs, '/logs/<spanid>')
api.add_resource(Prom, '/prom/<spanid>')

if __name__ == '__main__':
     app.run(port='5002')