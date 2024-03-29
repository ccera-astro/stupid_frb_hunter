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
import queue
import copy
import os
import random
import ephem

class blk(gr.sync_block):  # other base classes are basic_block, decim_block, interp_block
    """A FRB first-order detector block"""

    def __init__(self, fbsize=16,filename='/dev/null',fbrate=2500,chans=[1,7,14],
        thresh=5.0,minsmear=2.5e-3,declination=0.0,fake=False,longitude=76.03):  # only default arguments here
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
        self.aQueue = queue.Queue(maxsize=16)
        self.filename = filename
        
        #
        # we (somewhat arbitrarily) inspect a two-second window of
        #  channel data looking for pulses
        #
        self.two_seconds = int(fbrate*1.5)
        self.channels=[]
        self.chans = chans
        self.lchans = len(chans)
        self.declination = declination
        self.scnt = 0
        self.fbsize = fbsize
        self.fbrate = fbrate
        self.fake = fake
        self.longitude = longitude
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
    # Given longitude(decimal degrees as a float)
    #
    # Return the current sidereal time as a string with
    #  "," separated tokens
    #
    def cur_sidereal(self,longitude):
        longstr = "%02d" % int(longitude)
        longstr = longstr + ":"
        longitude = abs(longitude)
        frac = longitude - int(longitude)
        frac *= 60
        mins = int(frac)
        longstr += "%02d" % mins
        longstr += ":00"
        x = ephem.Observer()
        x.date = ephem.now()
        x.long = longstr
        jdate = ephem.julian_date(x)
        tokens=str(x.sidereal_time()).split(":")
        hours=int(tokens[0])
        minutes=int(tokens[1])
        seconds=int(float(tokens[2]))
        sidt = "%02d,%02d,%02d" % (hours, minutes, seconds)
        return (sidt)
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
        sidt = self.cur_sidereal(self.longitude)
        sids = sidt.split(",")
        sidh = float(sids[0])
        sidh += float(sids[1])/60.0
        sidh += float(sids[2])/3600.0
        fn = self.filename+"-"
        fn = fn + "%.1f-%04d%02d%02d-%02d%02d%05.3f-%.2f" % (declination, ltp.tm_year, ltp.tm_mon,
            ltp.tm_mday, ltp.tm_hour, ltp.tm_min, float(ltp.tm_sec)+frac, sidh)
        fp = open (fn+".dat", "w")
        for c in range(len(chans)):
            fp.write (str(chans[c])+"\n")
        fp.close()
    
    #
    # This is now largely a no-op except for logging.
    #
    def doAnalysis(self):
        if (self.aQueue.empty()):
            return None
        else:
            item = self.aQueue.get()
            self.logthispuppy(item["data"],item["time"])
                
    def work(self, input_items, output_items):
        """Do dedispersion/folding"""
        q = input_items[0]
        l = len(q)
        bndx = 0
        for i in range(int(l/self.flen)):
            #
            # For each channel
            #
            for c in range(self.flen):
                #
                # Add one sample to current channel
                #
                self.channels[c][self.scnt] = q[bndx]
                bndx += 1
            #
            # Once there are "enough" samples in the channels, do analysis
            #
            self.scnt += 1
            
            #
            # Each channel now has "two_seconds" (actually 1.5 right now) worth of samples in it
            #
            if (self.scnt >= self.two_seconds):
                # Analysis
                amused = 0
                amusingplaces = []
                
                #
                # For each of the "test" (amusing) channels
                #
                # Test for a spike that is "big" compared to mean
                #  in each of the "test" channels.  We use
                #  standard deviation and the "thresh" parameter
                #  to determine if spike is big enough
                #
                for amusing in self.chans:
                    #
                    # Channel average
                    #
                    cavg = np.mean(self.channels[amusing])
                    
                    #
                    # Channel STD
                    #
                    cstd = np.std(self.channels[amusing])
                    
                    #
                    # Find MAX in this channel
                    #
                    mx = np.max(self.channels[amusing])
                    
                    #
                    # How many sigma is max?
                    #
                    if ((mx-cavg) > cstd*self.thresh):
                        amused += 1
                        #
                        # Record location in the channel data
                        #
                        amusingplaces.append(np.argmax(self.channels[amusing]))
                    else:
                        break
                
                #
                # Only if we were amused in all amusing places
                #
                # On init we're giving a list of channels to inspect
                #  (or "be amused by").
                #
                # If we are amused (spike exceeds threshold) in all those channels
                #   do further analysis
                #
                if (amused >= self.lchans):
                    #
                    # Spike on lower-frequency channel must occur *after*
                    #  higher-frequency channel. Difference in positions
                    #  must be "significant".
                    #
                    # Because FRBs are dispersed, just like pulsars, the low-frequency channel
                    #  should be *later* than the higher-frequency channels.  We simply
                    #  use "sorted()" to enforce this rough ordering constraint.
                    #
                    if (amusingplaces == sorted(amusingplaces,reverse=True)):
                        lx = len(amusingplaces)-1
                        #
                        # Now, the distance (in samples) between the lowest frequency spike
                        #  and the highest must be > the minimum smear time implied by the
                        #  DM given on input to the program (and passed to use on init).
                        #
                        if ((amusingplaces[0] - amusingplaces[lx]) >= self.mindistance):
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
                            if (len(amusingplaces) > 0):
                                t -= (amusingplaces[0]*(1.0/self.fbrate))
                            d["time"] = t
                            self.aQueue.put(d)
                self.scnt = 0

        return len(q)
