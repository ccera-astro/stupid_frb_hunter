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

class blk(gr.sync_block):  # other base classes are basic_block, decim_block, interp_block
    """A pulsar folder/de-dispersion block"""

    def __init__(self, fbsize=16,filename='/dev/null',fbrate=2500,dms=[10.0,20.0,30.0,40.0,50.0],freq=408.0e6,bw=2.56e6,thresh=5.0):  # only default arguments here
        """arguments to this function show up as parameters in GRC"""
        gr.sync_block.__init__(
            self,
            name='Stupid FRB Hunter',   # will show up in GRC
            in_sig=[np.float32],
            out_sig=None
        )
        # if an attribute with the same name as a parameter is found,
        # a callback is registered (properties work, too).
        
        self.dmtable=dms
        self.filespec=filename
        self.flen = fbsize
        self.maxdelays = []
        self.delayincrs = []
        flower = (freq-(bw/2.0))/1.0e6
        fupper = (freq+(bw/2.0))/1.0e6
        self.ndms = len(self.dmtable)
        for dm in self.dmtable:
            smear = dm/2.41e-4 * (1.0/(flower*flower)-1.0/(fupper*fupper))
            smear = int(round(smear * fbrate))
            incr = int(round(float(smear)/float(fbsize)))
            self.maxdelays.append(smear)
            self.delayincrs.append(incr)
        self.obufs = np.zeros((self.ndms+1,fbrate*2))
        self.avgs = [0.0]*(self.ndms+1)
        self.ocount = 0
        self.thresh = thresh

    def work(self, input_items, output_items):
        """Do dedispersion/folding"""
        q = input_items[0]
        l = len(q)
        for i in range(l/self.flen):
            bndx = i*self.flen
            
            for x in range(self.ndms):
            #
            # Do delay/dedispersion logic
            #
                if (self.maxdelays[x] > 0):
                    outval = 0.0
                    #
                    # start at 1 because
                    #  we already know maxdelay > 1
                    #
                    for j in range(1,self.flen):
                        if ((self.maxdelays[x] - (self.delayincrs[x]*j)) <= 0):
                            outval += q[bndx+j]
                    self.maxdelays[x] -= 1
                else:
                    outval = sum(q[bndx:bndx+self.flen])
                
                
                self.obufs[x+1][self.ocount] = outval
            
            self.obufs[0][self.ocount] = sum(q[bndx:bndx+self.flen])
            self.ocount += 1
            if (self.ocount >= len(self.obufs[0])):
                self.ocount = 0
                
                for x in range(self.ndms+1):
                    avg = math.fsum(self.obufs[x])
                    avg /= len(self.obufs[x])
                    if (self.avgs[x] == 0):
                        self.avgs[x] = avg
                    avg += self.avgs[x]
                    avg /= 2.0
                    self.avgs[x] = avg
                    if ((max(self.obufs[x]) > avg*self.thresh) and x != 0):
                        t = time.gmtime()
                        d = {}
                        d["time"] = "%04d%02d%02d-%02d:%02d:%02d" % (t.tm_year,
                            t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
                        tseries = []
                        for obuf in self.obufs:
                            tseries.append(list(obuf))
                        d["tseries"] = tseries
                        d["dms"] = [0.0]+self.dmtable
                        d["trigger"] = (x,d["dms"][x])
                        fn = self.filespec+"-"+d["time"]+".json"
                        fp = open(fn, "w")
                        fp.write(json.dumps(d, indent=4)+"\n")
                        fp.close()  
                        break                  

            
        return len(q)
