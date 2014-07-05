#!/bin/python3

import os.path

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, GObject, Gtk, GdkX11, Gst, GstVideo

GObject.threads_init()
Gst.init(None)

class VideoController(GObject.GObject):
    __gsignals__ = {
            'playback-changed': ( GObject.SIGNAL_RUN_FIRST, None,
                (type(Gst.State.NULL),) )
        }
    
    def do_playback_changed(self, state):
        print('do_playback_changed', state)
    
    def __init__(self):
        GObject.GObject.__init__(self)
        # Set up pipeline and bus
        self.pipeline = Gst.Pipeline()
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message::eos', self.on_video_end)
        self.bus.connect('message::state-changed', self.on_state_changed)
        self.bus.connect('message::error', self.on_pipeline_error)
        self.bus.enable_sync_message_emission()
        self.bus.connect('sync-message::element', self.on_sync_message)
        
        self.playbin = Gst.ElementFactory.make('playbin', None)
        self.pipeline.add(self.playbin)
        #self.decodebin = Gst.ElementFactory.make('uridecodebin', None)
        #self.pipeline.add(self.decodebin)
        #self.decodebin.connect('pad-added', self.on_decodebin_pad_added)
        #self.playsink = Gst.ElementFactory.make('playsink', None)
        #self.pipeline.add(self.playsink)
        
        # Handle for, e.g., a DrawingArea widget to use for video display
        self.display = None
        self.display_xid = None
        #self.video_overlay = None
        
        # Handle for a slider (a Scale widget) to use for time display/seeking
        self.slider = None
        
        # Handle for a timer to regularly invoke UI updates
        self.timer_handle = None
        
        self.rate = 1.0
    
    def connect_display(self, display):
        """
        Connect a widget as the drawing window for the video.
        """
        self.display = display
        display.connect('realize', self.on_display_realize)
        #display.connect('expose-event', self.on_display_expose)
    
    def connect_slider(self, slider):
        self.slider = slider
        slider.connect('value-changed', self.on_slider_value_changed)
    
    def set_file(self, filename):
        filename = os.path.abspath(os.path.expanduser(filename))
        
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline.get_state(Gst.SECOND)
        self.playbin.set_property('uri', 'file://' + filename)
        self.pipeline.set_state(Gst.State.PAUSED)
        if (self.pipeline.get_state(Gst.SECOND)[0]
                != Gst.StateChangeReturn.SUCCESS):
            raise Exception('Unable to start pipeline')
        self.rate = 1.0
    
    def play(self):
        self.pipeline.set_state(Gst.State.PLAYING)
    
    def pause(self):
        self.pipeline.set_state(Gst.State.PAUSED)
    
    def toggle(self):
        status,state,pending = self.pipeline.get_state(0)
        if state == Gst.State.PAUSED:
            self.play()
        elif state == Gst.State.PLAYING:
            self.pause()
    
    def get_duration(self):
        try:
            success, nanosecs = self.pipeline.query_duration(Gst.Format.TIME)
            return float(nanosecs) / Gst.SECOND
        except Gst.QueryError:
            return 0
    
    def get_time(self):
        try:
            success, nanosecs = self.pipeline.query_position(Gst.Format.TIME)
            return float(nanosecs) / float(Gst.SECOND)
        except Gst.QueryError:
            return 0
    
    def get_frame_time(self):
        try:
            framerate = self.get_framerate()
            nanosecs, format = self.pipeline.query_position(Gst.Format.TIME)
            return (float(nanosecs / int(Gst.SECOND / framerate))
                / framerate)
        except Gst.QueryError:
            return 0
    
    def set_time(self, time):
        duration = self.get_duration()
        if time < 0.0:
            time = 0.0
        elif time > duration:
            time = duration
        self.pipeline.seek_simple( Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
            int(time * Gst.SECOND) )
    
    def set_rate(self, rate):
        self.pipeline.seek( rate, Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
            Gst.SeekType.NONE, 0,
            Gst.SeekType.NONE, 0 )
        self.rate = rate
    
    def get_dimensions(self):
        #frame = self.playbin.get_property('sample')
        #capsstruct = frame.get_caps().get_structure(0)
        video_caps = self.get_video_caps()
        if video_caps is None:
            return (0, 0)
        capsstruct = video_caps.get_structure(0)
        width = capsstruct.get_value('width')
        height = capsstruct.get_value('height')
        return (width, height)
    
    def get_framerate(self):
        #frame = self.playbin.get_property('sample')
        #capsstruct = frame.get_caps().get_structure(0)
        video_caps = self.get_video_caps()
        if video_caps is None:
            return 0.0
        capsstruct = video_caps.get_structure(0)
        (success, numerator, denominator) = capsstruct.get_fraction('framerate')
        return float(numerator)/float(denominator)
    
    def get_video_caps(self):
        #for pad in self.playsink.sinkpads:
        #    caps = pad.get_current_caps()
        #    if caps.to_string().startswith('video/'):
        #        return caps
        #return None
        playsink = self.playbin.get_by_name('playsink')
        video_pad = playsink.get_static_pad('video_sink')
        if video_pad is None:
            return None
        return video_pad.get_current_caps()
    
    def update_slider(self, update_all = False):
        if update_all:
            duration = self.get_duration()
            self.slider.set_range(0.0, duration)
            framerate = self.get_framerate()
            self.slider.set_increments(1.0/framerate, 1.0)
        self.slider.handler_block_by_func(self.on_slider_value_changed)
        self.slider.set_value(self.get_time())
        self.slider.handler_unblock_by_func(self.on_slider_value_changed)
        return True
    
    def on_slider_value_changed(self, slider):
        #print('on_slider_value_changed')
        self.set_time(slider.get_value())
    
    #def on_decodebin_pad_added(self, decodebin, src_pad):
    #    print('on_decodebin_pad_added')
    #    print('-->', src_pad.get_current_caps())
    #    sink_pad = self.playsink.get_compatible_pad(src_pad, None)
    #    src_pad.link(sink_pad)
    
    def on_display_realize(self, display):
        print('on_display_realize')
        self.display_xid = display.get_property('window').get_xid()
    
    #def on_display_expose(self, display):
    #    if self.video_overlay is not None:
    #        self.video_overlay.expose()
    
    def on_sync_message(self, bus, message):
        print('on_sync_message')
        if (message.get_structure().get_name() == 'prepare-window-handle'
                and self.display_xid is not None):
            #self.video_overlay = msg.src
            message.src.set_window_handle(self.display_xid)
    
    def on_state_changed(self, bus, message):
        if message.src != self.pipeline:
            return
        #print('on_state_changed')
        #print(message)
        prev_state,new_state,pending_state = message.parse_state_changed()
        #print(prev_state, new_state, pending_state)
        if pending_state != Gst.State.VOID_PENDING:
            # State transition is still in progress; let's wait until it's done
            return
        if prev_state == Gst.State.READY:
            # A new video has just loaded
            self.pipeline.seek(1.0, Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                Gst.SeekType.SET, 0,
                Gst.SeekType.NONE, 0)
            self.rate = 1.0
        if new_state == Gst.State.PAUSED:
            # Either the video has just loaded, or it was playing and is now
            # paused.
            if self.timer_handle is not None:
                # Stop auto-updating the timer
                GLib.source_remove(self.timer_handle)
                self.timer_handle = None
            # If a slider is used, update its time, range, and increments:
            if self.slider is not None:
                self.update_slider(True)
        elif new_state == Gst.State.PLAYING:
            # The video has started playing
            if self.slider is not None:
                # Set up a timer to periodically poll the video time and update
                # the slider value:
                self.timer_handle = (
                    GLib.timeout_add(100, self.update_slider, False) )
        if new_state != prev_state:
            self.emit('playback-changed', new_state)
    
    def on_video_end(self, bus, message):
        print('on_video_end')
        self.pipeline.set_state(Gst.State.PAUSED)
    
    def on_pipeline_error(self, bus, message):
        print('Pipeline error:', msg.parse_error())

if __name__ == '__main__':
    import sys
    vid_file = sys.argv[1]
    
    class ExampleGUI:
        def __init__(self, vid_file):
            self.window = Gtk.Window()
            self.window.connect('destroy', self.quit)
            self.vbox = Gtk.VBox()
            self.window.add(self.vbox)
            self.drawingarea = Gtk.DrawingArea()
            self.vbox.pack_start(self.drawingarea, True, True, 2)
            self.hbox = Gtk.HBox()
            self.vbox.pack_start(self.hbox, False, True, 2)
            self.button = Gtk.Button(stock=Gtk.STOCK_MEDIA_PLAY)
            self.button.connect('clicked', self.on_play_clicked)
            self.hbox.pack_start(self.button, False, True, 2)
            self.slider = Gtk.HScale()
            self.hbox.pack_start(self.slider, True, True, 2)
            
            self.vc = VideoController()
            self.vc.connect_display(self.drawingarea)
            self.vc.connect_slider(self.slider)
            self.vid_file = vid_file
        
        def run(self):
            self.window.show_all()
            self.vc.set_file(self.vid_file)
            Gtk.main()
        
        def quit(self, window):
            Gtk.main_quit()
        
        def on_play_clicked(self, button):
            self.vc.toggle()
    
    gui = ExampleGUI(vid_file)
    gui.run()

