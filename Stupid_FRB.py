"""
Embedded Python Blocks:

Each time this file is saved, GRC will instantiate the first class it finds
to get ports and parameters of your block. The arguments to __init__  will
be the parameters. All of them are required to have default values!
"""

import numpy as np
from gnuradio import gr
import time
import json
import math
import Queue
import copy
import os

class blk(gr.sync_block):  # other base classes are basic_block, decim_block, interp_block
    """A FRB first-order detector block"""

    def __init__(self, fbsize=16,filename='/dev/null',fbrate=2500,chans=[1,7,14],
        thresh=5.0,minsmear=2.5e-3,declination=0.0):  # only default arguments here
        """arguments to this function show up as parameters in GRC"""
        gr.sync_block.__init__(
            self,
            name='Stupid FRB Hunter',   # will show up in GRC
            in_sig=[np.float32],
            out_sig=None
        )
        # if an attribute with the same name as a parameter is found,
        # a callback is registered (properties work, too).
        
        #
        # We create a "work queue" of preliminary events
        #  The dequeue worker does further analysis before
        #  logging the event.
        self.aQueue = Queue.Queue(maxsize=16)
        self.filename = filename
        
        #
        # we (somewhat arbitrarily) inspect a two-second window of
        #  channel data looking for pulses
        #
        self.two_seconds = int(fbrate*2)
        self.channels=[]
        self.chans = chans
        self.lchans = len(chans)
        self.declination = declination
        self.scnt = 0
        self.fbsize = fbsize
        self.fbrate = fbrate
        #
        # The minimum time distance for detected
        #  pulses between the lowest and highest frequency
        #
        self.mindistance = minsmear * float(fbrate)
        self.mindistance = int(self.mindistance)
        for x in range(fbsize):
            self.channels.append([0.0]*self.two_seconds)
            
        self.thresh = thresh
        self.flen = fbsize

    #
    # Log an event
    #
    # We basically log the entire two-second channel buffer
    #
    def logthispuppy(self,chans,evt):
        q = self.thresh
        ltp = time.gmtime(evt)
        frac = evt-float(int(evt))
        declination = -99.00
        if (isinstance(self.declination, str) == True):
            if (os.path.isfile(self.declination)):
                f = open(self.declination, "r")
                dstr=f.readline()
                f.close()
                declination = float(dstr)
            else:
                try:
                    declination = float(self.declination)
                except:
                    declination = -99.00
        else:
            declination = float(self.declination)
        fn = self.filename+"-"
        fn = fn + "%7.2f-%04d%02d%02d_%02d%02d%05.3f" % (declination, ltp.tm_year, ltp.tm_mon,
            ltp.tm_mday, ltp.tm_hour, ltp.tm_min, float(ltp.tm_sec)+frac)
        fp = open (fn+".dat", "w")
        for c in range(self.lchans):
            fp.write (str(chans[c])+"\n")
        fp.close()
    
    def doAnalysis(self):
        if (self.aQueue.empty()):
            return None
        else:
            item = self.aQueue.get()
            goodcnt = 0
            for chan in item["data"]:
                avg = np.mean(chan)
                mx = np.max(chan)
                if (mx > avg*self.thresh):
                    goodcnt += 1
            if (goodcnt == self.lchans):
                self.logthispuppy(item["data"],item["time"])

    def work(self, input_items, output_items):
        """Do dedispersion/folding"""
        q = input_items[0]
        l = len(q)
        for i in range(int(l/self.flen)):
            bndx = i*self.flen
            for c in range(self.flen):
                self.channels[c][self.scnt] = q[bndx]
                bndx += 1
            self.scnt += 1
            if (self.scnt >= self.two_seconds):
                # Analysis
                amused = 0
                amusingplaces = []
                #
                # For each of the "test" (amusing) channels
                #
                # Test for a spike that is "big" compared to mean
                #  in each of the "test" channels
                #
                for amusing in self.chans:
                    #
                    # Channel average
                    #
                    cavg = np.mean(self.channels[amusing])
                    if ((np.max(self.channels[amusing])) / cavg > self.thresh):
                        amused += 1
                        amusingplaces.append(np.argmax(self.channels[amusing]))
                    else:
                        break
                
                #
                # Only if we were amused in all amusing places
                #
                if (amused >= self.lchans):
                    #
                    # Spike on lower-frequency channel must occur *after*
                    #  higher-frequency channel. Difference in positions
                    #  must be "significant"
                    #
                    if (amusingplaces[0] > amusingplaces[len(amusingplaces)-1] and
                        (amusingplaces[0] - amusingplaces[len(amusingplaces)-1]) > self.mindistance):
                            #
                            # Place this on a deeper-analysis queue
                            #
                            d = {}
                            d["data"] = copy.deepcopy(self.channels)
                            t = time.time()
                            #
                            # Adjust timestamp for pulse location within
                            #  the 2-second window.  This is only very
                            #  approximate.  But potentially allows better
                            #  coordination to other observatories.
                            #
                            t -= (self.amusingplaces[0]*(1.0/self.fbrate))
                            d["time"] = t
                            self.aQueue.put(d)
                self.scnt = 0

        return len(q)
