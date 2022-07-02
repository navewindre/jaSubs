# jaSubs
A "fork" of [InterSubs](https://github.com/oltodosel/interSubs), but for Japanese **only**.

Interactive subtitles for mpv, that was made to help study Japanese.

Easily tweaked and customizable.

**NOTE:** This project is unstable as for now and has some bugs

![showcase](./example.gif)

## Installation

Clone this repository in your mpv `scripts` folder:
```bash
$ cd ~/.config/mpv/scripts
$ git clone https://github.com/HasanAbbadi/jaSubs
```

Then make a symlink to the `lua` file:
```bash
$ pwd
~/.config/mpv/scripts
$ ln -s jaSubs/jaSubs.lua .
```

## Requirements
------------
   * mpv 0.27 (I don't know if it will work with mpv front-ends.)
   * Xorg (ignore for Mac users)
   * composite manager; `xcompmgr` or `picom`. (ignore for Mac users)
   * python => 3.6
   * python-pyqt5
   * python-numpy
   * python-requests
   * `sudachipy` and `sudachidict_core` (likely installed with `pip`)
   * lua
   * socat
   * pkill
   * xdotool (for hiding subtitles when minimizing mpv or switching window) 

## Usage
-----
* Start video with mpv & select subtitles.
* F3 to start/stop jaSubs.
	* Starts automatically with files/paths specified in jaSubs.lua
* Point cursor over the word to get popup with translation.
* F6 to hide/show without exiting.

Buttons bellow may be reassigned in `jaSubs_config.py`
-----
* Left-click  - show translation in your browser.
* Right-click - translate whole sentence
* Wheel+Ctrl  - resize subtitles.
* Wheel+Shift - change subtitles' vertical position.
* Wheel-click - cycle through auto_pause options.
* Wheel-click-left/right - +/- auto_pause_min_words. (fancy mouses)

## Notes
* Issues and Pull Request are highly appreciated



