"""Transparent loopback relay with safe status audit and one explicit response loss."""
import http.client,json,re,socket
from http.server import BaseHTTPRequestHandler


class RelayHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        return

    def do_GET(self):
        self.relay()

    def do_POST(self):
        self.relay()

    def relay(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.upstream_port,timeout=180)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<=size<=1024*1024:raise ValueError('invalid_size')
            body=self.rfile.read(size) if size else None
            headers={key:value for key,value in self.headers.items() if key.lower() not in {'host','connection','content-length'}}
            connection.request(self.command,self.path,body,headers)
            response=connection.getresponse();data=response.read();event={'path':self.path,'status':response.status}
            try:
                parsed=json.loads(data);code=parsed.get('error_category')
                if isinstance(code,str):event['error_category']=code if re.fullmatch('[a-z][a-z0-9_]{0,127}',code) else 'unclassified_error'
            except (ValueError,AttributeError):pass
            dropping=False
            if self.server.drop_flag and self.server.drop_flag.exists() and self.path.endswith('/execute') and body:
                request=json.loads(body)
                if request.get('operation') and response.status==200:
                    self.server.drop_flag.unlink();dropping=True;event['response_deliberately_lost']=True
            with self.server.audit.open('a',encoding='utf-8') as log:log.write(json.dumps(event)+'\n')
            if dropping:
                self.close_connection=True;self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
            self.send_response(response.status)
            self.send_header('Content-Type',response.getheader('Content-Type','application/json'));self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        finally:
            connection.close()
