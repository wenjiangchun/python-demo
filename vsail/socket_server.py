from twisted.internet import protocol, reactor, endpoints
from twisted.internet.protocol import Factory, connectionDone
from twisted.protocols import basic
from twisted.protocols import wire
import time
import logging
import configparser
import pika
from vsail_data_parser import VsailDataParser
from config_reader import VsailConfigReader
import binascii

logging.basicConfig(filename="socket_server.log", filemode="w", format="%(asctime)s %(name)s:%(levelname)s:%(message)s", datefmt="%y-%m-%d %H:%M:%S", level=logging.INFO)

def hex_to_str(s):
        '''
         将16进制转换为字符串
        '''
        return ''.join([chr(i) for i in [int(b, 16) for b in s.split(r'/x')[1:]]])

#Vsail车辆数据接收服务
class VsailServer(object):
    def __init__(self):
        self.reader = VsailConfigReader()
        self.init_rq = False
        self.rq_conn = self.init_rabbitmq(self.reader.rq_host)
        
    #初始化rabbitMQ
    def init_rabbitmq(self, rq_host):
        try:
            parameters = pika.ConnectionParameters(rq_host, port=self.reader.rq_port, virtual_host='vsail', credentials=pika.credentials.PlainCredentials(self.reader.rq_user, self.reader.rq_passd), heartbeat=0)
            connection = pika.BlockingConnection(parameters)
            logging.info('rabbitmq已连接')
            self.init_rq = True
            return connection
        except Exception as ex:
            logging.exception('rabbitmq初始化错误')
            logging.exception(ex)
            #异常出错不再往下执行
            raise Exception('rabbitmq初始化错误')
            
    def start(self):
        if self.init_rq:
            self.rt = reactor
            server_url = 'tcp:' + str(self.reader.socket_port)
            endpoints.serverFromString(reactor, server_url).listen(VsailDataFactory(self.rq_conn, self.reader))
            reactor.run()
            
    def stop(self):
        if self.init_rq:
            self.rt.stop()
            self.rq_conn.close()


class VsailDataFactory(protocol.Factory):
    def __init__(self, rq_conn, reader:VsailConfigReader):
        self.rq_conn = rq_conn
        self.reader = reader
    def buildProtocol(self, addr):
        channel = self.rq_conn.channel()
        logging.info('创建channel')
        return VsailDataHandler(channel, self.reader)


class VsailDataHandler(basic.NetstringReceiver):
    def __init__(self, channel, reader:VsailConfigReader):
        self.channel = channel
        self.reader = reader
        logging.info('创建消息处理器')
    def dataReceived(self, data):
        logging.info('开始接收消息...')
        message = data.decode('utf-8',"ignore")
        logging.info(data)
        logging.info('二进制转换16进制...')
        logging.info(binascii.b2a_hex(data))
        aa = str(binascii.b2a_hex(data), encoding="utf-8")
        bb = []
        for i, x in enumerate(aa):
            if i % 2 != 0:
                bb.append(str(aa[i-1]) + str(x))
        if message == 'exit':
            self.transport.loseConnection()
        else:
            try:
                logging.info(bb)
                v_message = ' '.join(bb)
                logging.info(v_message)
                parser = VsailDataParser(v_message)
                bus_data = parser.translate_to_json()
                print(bus_data)
                #判断报文是否有效
                if parser.is_valid():
                    #判断是历史消息还是实时消息
                    if parser.is_real() is True:
                        #如果是实时消息判断发送时间
                        self.channel.basic_publish(exchange=self.reader.rq_ex_real, routing_key='', body=v_message)
                        #如果是上线或下线 返回结果指令信息
                        if bus_data['type'] == 1 or bus_data['type'] == 2:
                            #self.transport.write('OK'.encode('utf-8'))
                            pass
                    else:
                        self.channel.basic_publish(exchange=self.reader.rq_ex_hist, routing_key='', body=v_message)
                        #pass
                else:
                    logging.warning('无效报文:' + message)
            except Exception:
                pass
    def connectionMade(self):  # 建立连接后的回调函数
        logging.info('客户端已连接')
    def connectionLost(self, reason=connectionDone):  # 断开连接后的反应
        logging.info('客户端已断开')
        self.channel.close()
        
if __name__ == '__main__':
    vsail_server = VsailServer()
    vsail_server.start()

