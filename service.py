from flask import Flask, jsonify, request
from flask_restful import Resource, Api
from requests.auth import HTTPBasicAuth
from flask_cors import CORS
import datetime
import json
import urllib
import requests
import redis

app = Flask(__name__)
api = Api(app)
CORS(app)
HOST = 'http://10.240.201.100'
PROM_PORT = '9091'
ES_PORT = '9200'
rd = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

"""
Define Prometheus query.
"""

class PromQuery:
  safe_chars = '()_-&~*'
  time_gap = 900
  step = '10'

  memory = '(sum(node_memory_MemTotal_bytes{{instance=~"{0}:9100"}})' \
    '- sum(node_memory_MemFree_bytes{{instance=~"{0}:9100"}}' \
      '+node_memory_Buffers_bytes{{instance=~"{0}:9100"}}' \
        '+node_memory_Cached_bytes{{instance=~"{0}:9100"}}) )' \
          '/ sum(node_memory_MemTotal_bytes{{instance=~"{0}:9100"}}) * 100'

  cpu = '100 - (avg  (irate(node_cpu_seconds_total' \
    '{{mode="idle",instance=~"{0}.*"}}[1m])) * 100)'
  
  filesystem_usage = 'sum (container_fs_limit_bytes{{instance=~"{0}:8080"}}' \
    '- container_fs_usage_bytes{{instance=~"{0}:8080"}})' \
      '/ sum(container_fs_limit_bytes{{instance=~"{0}:8080"}})'

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
    span_info = json.loads(get_span_info(spanid))
    if span_info['error'] == 0:
      span_info = span_info['data']

      data_from_cache = rd.get('{0}-*'.format(spanid)) if span_info['isRoot'] \
        else rd.get(form_log_key(span_info['traceid'], spanid))

      if data_from_cache:
        return jsonify({
            'error' : 0,
            'data' : data_from_cache,
            'message' : 'Records retrieved'
          })

      # convert millisecond epoch timestamp to human date
      time = datetime.datetime.fromtimestamp(span_info['start_time']/1000).date() 
      try:
      query = 'vsmart-{0}.*/_search/?size=1000&q=traceid:'.format(time.strftime('%Y.%m'))
      # request url
      url = HOST + ':' + ES_PORT + '/' + query + span_info['traceid']
      r = json.loads(requests.get(url).text)
      if r['hits']['total'] > 0:
        data = [i['_source'] for i in r['hits']['hits']]
        sub_group_data = sub_group([i['_source'] for i in r['hits']['hits']])
        
        for key, value in sub_group_data.items():
          set_to_cache(form_log_key(span_info['traceid'], key), json.dumps(value))

        return jsonify({
          'error' : 0,
          'data' : sub_group_data[spanid] if not span_info['isRoot'] else data,
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
  def get(self, spanid, metric_name):
    span_info = json.loads(get_span_info(spanid))
    if span_info['error'] == 0:
      span_info = span_info['data']

      data_from_cache = rd.get(form_metric_key(span_info['traceid'], metric_name, span_info['host_ip']))

      if data_from_cache:
        return jsonify({
            'error' : 0,
            'data' : data_from_cache,
            'message' : 'Records retrieved'
          })

      # try:
      # convert millisecond epoch start_time, end_time timestamp
      # to second epoch timestamp
      start_time = int(span_info['start_time']/1000)
      end_time = int(span_info['end_time']/1000)
      # request url
      url = HOST + ':' + PROM_PORT + '/api/v1/query_range?query=' \
        + urllib.parse.quote(getattr(PromQuery,metric_name).format(span_info['host_ip']), safe=PromQuery.safe_chars) \
          + '&start=' + str(start_time - PromQuery.time_gap) \
            + '&end=' + str(end_time + PromQuery.time_gap) + '&step=' + PromQuery.step
      # authentication is optional
      r = json.loads(requests.get(url, auth=HTTPBasicAuth('admin', 'QwPnMAEGNVVaN5OinDikz8ilYRfJvUmY9dAaYqTy')).text)
      if r['status'] == 'success':
        set_to_cache(form_metric_key(span_info['traceid'], metric_name, span_info['host_ip']),\
          json.dumps([r['data']['result'][0]['values']]))
        return jsonify({
          'error' : 0,
          'data' : [r['data']['result'][0]['values']],
          'message' : 'Records retrieved'
        })
      return jsonify({
        'error' : 0,
        'message' : 'No record found'
      })
      # except:
      #   return jsonify({
      #     'error' : 1,
      #     'message' : 'There was an error'
      #   })
    return jsonify({
      'error' : 1,
      'message' : span_info['message']
    })

"""
Get Span start_time and end_time from spanid
"""
def get_span_info(spanid):
  url = HOST + ':' + ES_PORT + '/jaeger-*/_search?q=spanID:' + spanid
  # try:
  r = json.loads(requests.get(url).text)
  if r['hits']['total'] > 0:
    return json.dumps({
      'error' : 0,
      'message' : 'OK',
      'data' : {
        'isRoot' : r['hits']['hits'][0]['_source']['spanID'] == \
          r['hits']['hits'][0]['_source']['traceID'],
        'traceid' : r['hits']['hits'][0]['_source']['traceID'],
        'host_ip' : r['hits']['hits'][0]['_source']['process']['tags'][2]['value'],
        'start_time' : r['hits']['hits'][0]['_source']['startTimeMillis'],
        'end_time' :  r['hits']['hits'][0]['_source']['startTimeMillis'] \
          + r['hits']['hits'][0]['_source']['duration']
      }
    })
  return json.dumps({
    'error' : 1,
    'message' : 'Span not found'
  })
  # except:
  #   return json.dumps({
  #     'error' : 1,
  #     'message' : 'There was an error'
  #   })

def set_to_cache(key, value):
  rd.set(key, value, nx=True, ex=900) # set expiration time to 15mins

def form_log_key(traceid, spanid):
  return '{0}-{1}-logs'.format(traceid, spanid)

def form_metric_key(traceid, metric_name, host_ip):
  return '{0}-metric-{1}-{2}'.format(traceid, metric_name, host_ip)

def sub_group(data):
  result = {}
  for item in data:
    try:
      if item not in result[item['spanid']]:
        result[item['spanid']].append(item)
    except:
      result[item['spanid']] = list()
      result[item['spanid']].append(item)
  return result

api.add_resource(Logs, '/logs/<spanid>')
api.add_resource(Prom, '/prom/<spanid>/<metric_name>')

if __name__ == '__main__':
  app.run(port='5002')