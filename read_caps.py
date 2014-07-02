#!/bin/bash/python3

import time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

GObject.threads_init()
Gst.init(None)

class CapsReader:
    def __init__(self, filename):
        start = time.time()
        self.pipeline = Gst.Pipeline()
        
        # The full pipeline is: decoder ! funnel ! sink
        # The funnel gives us as many sinks as we need for each source pad from
        # the decoder, sending them all ultimately into the fakesink
        self.decoder = Gst.ElementFactory.make('uridecodebin', None)
        self.funnel = Gst.ElementFactory.make('funnel', None)
        self.sink = Gst.ElementFactory.make('fakesink', None)
        
        self.pipeline.add(self.decoder)
        self.pipeline.add(self.funnel)
        self.pipeline.add(self.sink)
        
        self.funnel.link(self.sink)
        
        self.decoder.set_property('uri', 'file://' + filename)
        
        self.decoder.connect('pad-added', self.on_decoder_pad_added)
        setup_time = time.time() - start
        print('Setup time is', setup_time, 'seconds')
        
        start = time.time()
        self.pipeline.set_state(Gst.State.PAUSED)
        if self.pipeline.get_state(Gst.SECOND/10)[0] != Gst.StateChangeReturn.SUCCESS:
            #raise Exception('Unable to start pipeline')
            print('Unable to start pipeline')
        state_time = time.time() - start
        print('Pipeline start time is', state_time, 'seconds')
    
    def on_decoder_pad_added(self, decoder, pad):
        funnel_pad = self.funnel.get_compatible_pad(pad, None)
        pad.link(funnel_pad)
    
    def get_duration(self):
        dur_ns = self.pipeline.query_duration(Gst.Format.TIME)[1]
        return float(dur_ns) / float(Gst.SECOND)
    
    def get_all_caps(self):
        capslist = [pad.get_current_caps() for pad in self.decoder.srcpads]
        video_caps = []
        audio_caps = []
        for caps in capslist:
            string = caps.to_string()
            if string.startswith('audio/'):
                audio_caps.append(caps_structure_to_dict(caps))
            elif string.startswith('video/'):
                video_caps.append(caps_structure_to_dict(caps))
        return (capslist, video_caps, audio_caps)
    
    def get_video_caps(self):
        return self.get_all_caps()[1]
    
    def get_audio_caps(self):
        return self.get_all_caps()[2]

def caps_structure_to_dict(caps):
    struct = caps.get_structure(0)
    d = {}
    for i in range(struct.n_fields()):
        key = struct.nth_field_name(i)
        if struct.get_field_type(key).name == 'GstFraction':
            # This doesn't get handled properly
            # Seems like a Python type for GstFractions isn't implemented yet?
            (spam, numerator, denominator) = struct.get_fraction(key)
            # We can store it as a tuple
            d[key] = (numerator, denominator)
        else:
            d[key] = struct.get_value(key)
    return d

def read_caps(filename):
    reader = CapsReader(filename)
    (allcaps, video_caps, audio_caps) = reader.get_all_caps()
    return {'duration': reader.get_duration(), 'video': video_caps,
            'audio': audio_caps}

if __name__ == '__main__':
    import sys
    vid_file = sys.argv[1]
    start = time.time()
    res = read_caps(vid_file)
    delta = time.time() - start
    print(res)
    print(delta, 'seconds elapsed')

