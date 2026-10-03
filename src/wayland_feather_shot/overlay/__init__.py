"""The region overlay: the frozen screenshot shown fullscreen, where a region
is selected and annotated in place.

window.py holds OverlayWindow and its input; the window is assembled from
mixins, one per concern (view, controls, text, draw). canvas.py and
layout.py are the snapshot widget and the GTK-free placement of the bars.
Nothing is imported here, so the GTK-free parts load without GTK.
"""
