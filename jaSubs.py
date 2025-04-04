#! /usr/bin/env python

# v. 2.10
# Interactive subtitles for `mpv` for language learners.

import os, subprocess, sys
import random, re, time
import requests
import threading, queue
import calendar, math, base64
import numpy
import ast

from urllib.parse import quote
from json import loads
from json.decoder import JSONDecodeError

import warnings
from six.moves import urllib

from PyQt5.QtCore import Qt, QThread, QObject, pyqtSignal, pyqtSlot, QSize, QEvent
from PyQt5.QtWidgets import QApplication, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget
from PyQt5.QtGui import QPalette, QPaintEvent, QPainter, QPainterPath, QFont, QFontMetrics, QColor, QPen, QBrush

# Import Japanese tokinizer
from sudachipy import tokenizer
from sudachipy import dictionary
tokenizer_obj = dictionary.Dictionary(dict="full").create(tokenizer.Tokenizer.SplitMode.C)

form = 0
was_paused = 0
tthread = 0
app = 0
current_text = ''

pth = os.path.expanduser('~/.config/mpv/scripts/')
os.chdir(pth)
import config as config

def katakana_to_hiragana(text):
  return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c for c in text)

# returns ([[word: reading, translation]..], [morphology = '', gender = ''])
# jisho.org
def jisho(word):
    DOMAIN = 'jisho.org'
    VERSION = '1'

    base_url = f'https://{DOMAIN}/api/v{VERSION}'

    def get(url, params=None):
        if params is None:
            params = {}

        response = requests.get(
            url,
            params=params,
        )

        json = response.json()
        if response.status_code != 200:
            raise APIException(response.status_code,
                               response.content.decode())

        try:
            word = json['data'][0]['japanese'][0]['word'] + ': ' + json['data'][0]['japanese'][0]['reading']
            reading = json['data'][0]['japanese'][0]['reading']
            translations = json['data'][0]['senses'][0]['english_definitions']
            pairs = [[word, '']]
            for definition in translations:
              pairs.append(['', definition])

            return pairs, [reading, '']
        except:
            return  [['No translation Found', ''], ['', '']]

    def search(keyword):
        url = f'{base_url}/search/words'
        params = {'keyword': keyword} if keyword else {}
        return get(url, params=params)

    return search(word)


# offline dictionary with word \t translation
def tab_divided_dict(word):
  if word in offdict:
    tr = re.sub('<.*?>', '', offdict[word]) if config.tab_divided_dict_remove_tags_B else offdict[word]
    tr = tr.replace('\\n', '\n').replace('\\~', '~')
    return [[tr, '-']], ['', '']
  else:
    return [], ['', '']

# Google
# https://github.com/Saravananslb/py-googletranslation
class TokenAcquirer:
    """Google Translate API token generator

    translate.google.com uses a token to authorize the requests. If you are
    not Google, you do have this token and will have to pay for use.
    This class is the result of reverse engineering on the obfuscated and
    minified code used by Google to generate such token.

    The token is based on a seed which is updated once per hour and on the
    text that will be translated.
    Both are combined - by some strange math - in order to generate a final
    token (e.g. 464393.115905) which is used by the API to validate the
    request.

    This operation will cause an additional request to get an initial
    token from translate.google.com.

    Example usage:
        >>> from pygoogletranslation.gauthtoken import TokenAcquirer
        >>> acquirer = TokenAcquirer()
        >>> text = 'test'
        >>> tk = acquirer.do(text)
        >>> tk
        464393.115905
    """

    def __init__(self, tkk='0', tkk_url='https://translate.google.com/translate_a/element.js', proxies=None):

        if proxies is not None:
            self.proxies = proxies
        else:
            self.proxies = None

        r = requests.get(tkk_url, proxies=self.proxies)

        if r.status_code == 200:
            re_tkk = re.search("(?<=tkk=\\')[0-9.]{0,}", str(r.content.decode("utf-8")))            
            if re_tkk:
                self.tkk = re_tkk.group(0)
            else:
                self.tkk = '0'
        else:
            self.tkk = '0'


    def _xr(self, a, b):
            size_b = len(b)
            c = 0
            while c < size_b - 2:
                d = b[c + 2]
                d = ord(d[0]) - 87 if 'a' <= d else int(d)
                d = self.rshift(a, d) if '+' == b[c + 1] else a << d
                a = a + d & 4294967295 if '+' == b[c] else a ^ d

                c += 3
            return a

    def acquire(self, text):
        a = []
        # Convert text to ints
        for i in text:
            val = ord(i)
            if val < 0x10000:
                a += [val]
            else:
                # Python doesn't natively use Unicode surrogates, so account for those
                a += [
                    math.floor((val - 0x10000) / 0x400 + 0xD800),
                    math.floor((val - 0x10000) % 0x400 + 0xDC00)
                ]

        b = self.tkk
        d = b.split('.')
        b = int(d[0]) if len(d) > 1 else 0

        # assume e means char code array
        e = []
        g = 0
        size = len(a)
        while g < size:
            l = a[g]
            # just append if l is less than 128(ascii: DEL)
            if l < 128:
                e.append(l)
            # append calculated value if l is less than 2048
            else:
                if l < 2048:
                    e.append(l >> 6 | 192)
                else:
                    # append calculated value if l matches special condition
                    if (l & 64512) == 55296 and g + 1 < size and \
                            a[g + 1] & 64512 == 56320:
                        g += 1
                        l = 65536 + ((l & 1023) << 10) + (a[g] & 1023)  # This bracket is important
                        e.append(l >> 18 | 240)
                        e.append(l >> 12 & 63 | 128)
                    else:
                        e.append(l >> 12 | 224)
                    e.append(l >> 6 & 63 | 128)
                e.append(l & 63 | 128)
            g += 1
        a = b
        for i, value in enumerate(e):
            a += value
            a = self._xr(a, '+-a^+6')
        a = self._xr(a, '+-3^+b+-f')
        a ^= int(d[1]) if len(d) > 1 else 0
        if a < 0:  # pragma: nocover
            a = (a & 2147483647) + 2147483648
        a %= 1000000  # int(1E6)
        return '{}.{}'.format(a, a ^ b)

    def do(self, text):
        tk = self.acquire(text)
        return tk

    
    def rshift(self, val, n):
        """python port for '>>>'(right shift with padding)
        """
        return (val % 0x100000000) >> n

# translate.google.com
def google(word):
  word = word.replace('\n', ' ').strip()
  url = 'https://translate.google.com/translate_a/single?client=t&sl={lang_from}&tl={lang_to}&hl={lang_to}&dt=at&dt=bd&dt=ex&dt=ld&dt=md&dt=qca&dt=rw&dt=rm&dt=ss&dt=t&ie=UTF-8&oe=UTF-8&otf=1&pc=1&ssel=3&tsel=3&kc=2&q={word}'.format(lang_from = config.lang_from, lang_to = config.lang_to, word = quote(word))

  pairs = []
  fname = 'urls/' + url.replace('/', "-")
  try:
    if ' ' in word:
      raise Exception('skip saving')
    
    p = open(fname).read().split('=====/////-----')
    try:
      word_descr = p[1].strip()
    except:
      word_descr = ''

    for pi in p[0].strip().split('\n\n'):
      pi = pi.split('\n')
      pairs.append([pi[0], pi[1]])
  except:
    acquirer = TokenAcquirer()
    tk = acquirer.do(word)

    url = '{url}&tk={tk}'.format(url = url, tk = tk)
    p = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.167 Safari/537.36'}).text
    p = loads(p)

    try:
      pairs.append([p[0][0][0], p[0][0][1]])
    except:
      pass

    if p[1] != None:
      for translations in p[1]:
        for translation in translations[2]:
          try:
            t1 = translation[5] + ' ' + translation[0]
          except:
            t1 = translation[0]

          t2 = ', '.join(translation[1])

          if not len(t1):
            t1 = '-'
          if not len(t2):
            t2 = '-'

          pairs.append([t1, t2])

    word_descr = ''

  return pairs, ['', '']

def pause_on_popup():
  global was_paused
  if mpv_pause_status():
    was_paused = 1
  mpv_pause()

def resume_on_popup():
  global was_paused
  if not was_paused:
    mpv_resume()
  was_paused = 0

def mpv_pause():
  os.system('echo \'{ "command": ["set_property", "pause", true] }\' | socat - "' + mpv_socket + '" > /dev/null')

def mpv_resume():
  os.system('echo \'{ "command": ["set_property", "pause", false] }\' | socat - "' + mpv_socket + '" > /dev/null')

def mpv_pause_status():
  stdoutdata = subprocess.getoutput('echo \'{ "command": ["get_property", "pause"] }\' | socat - "' + mpv_socket + '"')

  try:
    return loads(stdoutdata)['data']
  except:
    return mpv_pause_status()

def mpv_fullscreen_status():
  stdoutdata = subprocess.getoutput('echo \'{ "command": ["get_property", "fullscreen"] }\' | socat - "' + mpv_socket + '"')

  try:
    return loads(stdoutdata)['data']
  except:
    return mpv_fullscreen_status()

def mpv_message(message, timeout = 3000):
  os.system('echo \'{ "command": ["show-text", "' + message + '", "' + str(timeout) + '"] }\' | socat - "' + mpv_socket + '" > /dev/null')

def stripsd2(phrase):
  return ''.join(e for e in phrase.strip().lower() if e == ' ' or (e.isalnum() and not e.isdigit())).strip()

def r2l(l):
  l2 = ''

  try:
    l2 = re.findall('(?!%)\W+$', l)[0][::-1]
  except:
    pass

  l2 += re.sub('^\W+|(?!%)\W+$', '', l)

  try:
    l2 += re.findall('^\W+', l)[0][::-1]
  except:
    pass
  
  return l2

def split_long_lines(line, chunks = 2, max_symbols_per_line = False):
  if max_symbols_per_line:
    chunks = 0
    while 1:
      chunks += 1
      new_lines = []
      for i in range(chunks):
        new_line = ' '.join(numpy.array_split(line.split(' '), chunks)[i])
        new_lines.append(new_line)

      if len(max(new_lines, key = len)) <= max_symbols_per_line:
        return '\n'.join(new_lines)
  else:
    new_lines = []
    for i in range(chunks):
      new_line = ' '.join(numpy.array_split(line.split(' '), chunks)[i])
      new_lines.append(new_line)

    return '\n'.join(new_lines)

def dir2(name):
  print('\n'.join(dir( name )))
  exit()

class thread_subtitles(QObject):
  update_subtitles = pyqtSignal(bool, bool)
  update_screen_sig = pyqtSignal()

  @pyqtSlot()
  def main(self):
    global subs

    was_hidden = 0
    inc = 0
    auto_pause_2_ind = 0
    last_updated = time.time()

    while 1:
      time.sleep(config.update_time)
      # hide subs when mpv isn't in focus or in fullscreen
      if inc * config.update_time > config.focus_checking_time - 0.0001:
        process_output = subprocess.getoutput('xdotool getwindowfocus getwindowname')
        # "Add" - anki add card dialog
        while ( (process_output != 'Add') and 'mpv' not in process_output ) or (config.hide_when_not_fullscreen_B and not mpv_fullscreen_status()) or (os.path.exists(mpv_socket + '_hide')):
          if not was_hidden:
            self.update_subtitles.emit(True, False)
            was_hidden = 1
          else:
            time.sleep(config.focus_checking_time)
          process_output = subprocess.getoutput('xdotool getwindowfocus getwindowname')
        inc = 0
        self.update_screen_sig.emit()
      inc += 1

      if was_hidden:
        was_hidden = 0
        self.update_subtitles.emit(False, False)
        continue

      try:
        tmp_file_subs = open(sub_file).read()
      except:
        continue

      if config.extend_subs_duration2max_B and not len(tmp_file_subs):
        if not config.extend_subs_duration_limit_sec:
          continue
        if config.extend_subs_duration_limit_sec > time.time() - last_updated:
          continue

      last_updated = time.time()

      while tmp_file_subs != subs:
        if config.auto_pause == 2:
          if not auto_pause_2_ind and len(re.sub(' +', ' ', stripsd2(subs.replace('\n', ' '))).split(' ')) > config.auto_pause_min_words - 1 and not mpv_pause_status():
            mpv_pause()
            auto_pause_2_ind = 1

          if auto_pause_2_ind and mpv_pause_status():
            break

          auto_pause_2_ind = 0

        subs = tmp_file_subs
        if config.auto_pause == 1:
          if len(re.sub(' +', ' ', stripsd2(subs.replace('\n', ' '))).split(' ')) > config.auto_pause_min_words - 1:
            mpv_pause()

        self.update_subtitles.emit(False, False)

class thread_translations(QObject):
  get_translations = pyqtSignal(str, int, bool)

  @pyqtSlot()
  def main(self):
    while 1:
      to_new_word = False

      try:
        word, globalX = config.queue_to_translate.get(False)
      except:
        time.sleep(config.update_time)
        continue

      # changing cursor to hourglass during translation
      QApplication.setOverrideCursor(Qt.WaitCursor)

      threads = []
      for translation_function_name in config.translation_function_names:
        threads.append(threading.Thread(target = globals()[translation_function_name], args = (word,)))
      for x in threads:
        x.start()
      while any(thread.is_alive() for thread in threads):
        if config.queue_to_translate.qsize():
          to_new_word = True
          break
        time.sleep(config.update_time)

      QApplication.restoreOverrideCursor()

      if to_new_word:
        continue

      if config.block_popup:
        continue

      self.get_translations.emit(word, globalX, False)

# drawing layer
# because can't calculate outline with precision
class drawing_layer(QLabel):
  def __init__(self, line, subs, parent=None):
    super().__init__(None)
    self.line = line
    self.setStyleSheet(config.style_subs)
    self.psuedo_line = 0

  def draw_text_n_outline(self, painter: QPainter, x, y, outline_width, outline_blur, text):
    outline_color = QColor(config.outline_color)

    font = self.font()
    text_path = QPainterPath()
    text_path.addText(x, y, font, text)

    # draw blur
    range_width = range(outline_width, outline_width + outline_blur)
    # ~range_width = range(outline_width + outline_blur, outline_width, -1)

    for width in range_width:
      if width == min(range_width):
        alpha = 200
      else:
        alpha = (max(range_width) - width) / max(range_width) * 200
        alpha = int(alpha)

      blur_color = QColor(outline_color.red(), outline_color.green(), outline_color.blue(), alpha)
      blur_brush = QBrush(blur_color, Qt.SolidPattern)
      blur_pen = QPen(blur_brush, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

      painter.setPen(blur_pen)
      painter.drawPath(text_path)

    # draw outline
    outline_color = QColor(outline_color.red(), outline_color.green(), outline_color.blue(), 255)
    outline_brush = QBrush(outline_color, Qt.SolidPattern)
    outline_pen = QPen(outline_brush, outline_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    painter.setPen(outline_pen)
    painter.drawPath(text_path)

    # draw text
    color = self.palette().color(QPalette.Text)
    painter.setPen(color)
    painter.drawText(x, y, text)

  if config.outline_B:
    def paintEvent(self, evt: QPaintEvent):
      if not self.psuedo_line:
        self.psuedo_line = 1
        return

      x = y = 0
      y += self.fontMetrics().ascent()
      painter = QPainter(self)

      self.draw_text_n_outline(
        painter,
        x,
        y + config.outline_top_padding - config.outline_bottom_padding,
        config.outline_thickness,
        config.outline_blur,
        text = self.line
        )

    def resizeEvent(self, *args):
      self.setFixedSize(
        self.fontMetrics().width(self.line),
        self.fontMetrics().height() +
          config.outline_bottom_padding +
          config.outline_top_padding
        )

    def sizeHint(self):
      return QSize(
        self.fontMetrics().width(self.line),
        self.fontMetrics().height()
        )

class events_class(QLabel):
  mouseHover = pyqtSignal(str, int, bool)
  redraw = pyqtSignal(bool, bool)

  def __init__(self, word, subs, skip = False, parent=None, reading=None):
    super().__init__(word)
    self.setMouseTracking(True)
    self.word = word
    self.subs = subs
    self.skip = skip
    if reading is not None:
      self.reading = reading
    else:
      self.reading = ""
    self.highlight = False

    self.setStyleSheet('background: transparent; color: transparent;')

  def highligting(self, color, underline_width):
    color = QColor(color)
    color = QColor(color.red(), color.green(), color.blue(), 200)
    painter = QPainter(self)

    if config.hover_underline:
      font_metrics = QFontMetrics(self.font())
      text_width = font_metrics.width(self.word)
      text_height = font_metrics.height()

      brush = QBrush(color)
      pen = QPen(brush, underline_width, Qt.SolidLine, Qt.RoundCap)
      painter.setPen(pen)
      if not self.skip:
        painter.drawLine(0, text_height - underline_width, text_width, text_height - underline_width)

    if config.hover_hightlight:
      x = y = 0
      y += self.fontMetrics().ascent()

      painter.setPen(color)
      painter.drawText(x, y + config.outline_top_padding - config.outline_bottom_padding, self.word)

  if config.outline_B:
    def paintEvent(self, evt: QPaintEvent):
      if self.highlight:
        self.highligting(config.hover_color, config.hover_underline_thickness)

  #####################################################

  def resizeEvent(self, event):
    text_height = self.fontMetrics().height()
    text_width = self.fontMetrics().width(self.word)

    self.setFixedSize(text_width, text_height + config.outline_bottom_padding + config.outline_top_padding)

  def enterEvent(self, event):
    if not self.skip:
      self.highlight = True
      self.repaint()
      config.queue_to_translate.put((self.word, event.globalX()))

  @pyqtSlot()
  def leaveEvent(self, event):
    if not self.skip:
      self.highlight = False
      self.repaint()

      config.scroll = {}
      self.mouseHover.emit('', 0, False)
      QApplication.restoreOverrideCursor()

  def wheel_scrolling(self, event):
    if event.y() > 0:
      return 'ScrollUp'
    if event.y():
      return 'ScrollDown'
    if event.x() > 0:
      return 'ScrollLeft'
    if event.x():
      return 'ScrollRight'

  def wheelEvent(self, event):
    for mouse_action in config.mouse_buttons:
      if self.wheel_scrolling(event.angleDelta()) == mouse_action[0]:
        if event.modifiers() == eval('Qt.%s' % mouse_action[1]):
          exec('self.%s(event)' % mouse_action[2])

  def mousePressEvent(self, event):
    for mouse_action in config.mouse_buttons:
      if 'Scroll' not in mouse_action[0]:
        if event.button() == eval('Qt.%s' % mouse_action[0]):
          if event.modifiers() == eval('Qt.%s' % mouse_action[1]):
            exec('self.%s(event)' % mouse_action[2])

  #####################################################

  def f_show_in_browser(self, event):
    config.avoid_resuming = True
    os.system(config.show_in_browser.replace('${word}', self.word))

  def f_copy_reading(self, event):
    os.system('echo "' + self.reading + '" | xclip -selection clipboard')

  def f_auto_pause_options(self, event):
    if config.auto_pause == 2:
      config.auto_pause = 0
    else:
      config.auto_pause += 1
    mpv_message('auto_pause: %d' % config.auto_pause)

  @pyqtSlot()
  def f_subs_screen_edge_padding_decrease(self, event):
    config.subs_screen_edge_padding -= 5
    mpv_message('subs_screen_edge_padding: %d' % config.subs_screen_edge_padding)
    self.redraw.emit(False, True)

  @pyqtSlot()
  def f_subs_screen_edge_padding_increase(self, event):
    config.subs_screen_edge_padding += 5
    mpv_message('subs_screen_edge_padding: %d' % config.subs_screen_edge_padding)
    self.redraw.emit(False, True)

  @pyqtSlot()
  def f_font_size_decrease(self, event):
    config.style_subs = re.sub('font-size: (\d+)px;', lambda size: [ 'font-size: %dpx;' % ( int(size.group(1)) - 1 ), mpv_message('font: %s' % size.group(1)) ][0], config.style_subs, flags = re.I)
    self.redraw.emit(False, True)

  @pyqtSlot()
  def f_font_size_increase(self, event):
    config.style_subs = re.sub('font-size: (\d+)px;', lambda size: [ 'font-size: %dpx;' % ( int(size.group(1)) + 1 ), mpv_message('font: %s' % size.group(1)) ][0], config.style_subs, flags = re.I)
    self.redraw.emit(False, True)

  @pyqtSlot()
  def f_translation_full_sentence(self, event):
    self.mouseHover.emit(self.subs , event.globalX(), True)

  def f_auto_pause_min_words_decrease(self, event):
    config.auto_pause_min_words -= 1
    mpv_message('auto_pause_min_words: %d' % config.auto_pause_min_words)

  def f_auto_pause_min_words_increase(self, event):
    config.auto_pause_min_words += 1
    mpv_message('auto_pause_min_words: %d' % config.auto_pause_min_words)


class main_class(QWidget):
  class PopupThread(QThread):
    def setPopup(self, popup):
      self.popup = popup
    def run(self):
      self.popup.show()

  def __init__(self):
    super().__init__()

    self.thread_subs = QThread()
    self.obj = thread_subtitles()
    self.obj.update_subtitles.connect(self.render_subtitles)
    self.obj.update_screen_sig.connect(update_screen)
    self.obj.moveToThread(self.thread_subs)
    self.thread_subs.started.connect(self.obj.main)
    self.thread_subs.start()

    self.thread_translations = QThread()
    self.obj2 = thread_translations()
    self.obj2.get_translations.connect(self.render_popup)
    self.obj2.moveToThread(self.thread_translations)
    self.thread_translations.started.connect(self.obj2.main)
    self.thread_translations.start()

    # start the forms
    self.subtitles_base()
    self.subtitles_base2()
    self.popup_base()

  def clearLayout(self, layout):
    if layout == 'subs':
      layout = self.subtitles_vbox
      self.subtitles.hide()
    elif layout == 'subs2':
      layout = self.subtitles_vbox2
      self.subtitles2.hide()
    elif layout == 'popup':
      layout = self.popup_vbox
      self.popup.hide()

    if layout is not None:
      while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()

        if widget is not None:
          widget.deleteLater()
        else:
          self.clearLayout(item.layout())

  def subtitles_base(self):
    self.subtitles = QFrame()
    self.subtitles.setAttribute(Qt.WA_TranslucentBackground)
    self.subtitles.setWindowFlags(Qt.X11BypassWindowManagerHint)
    self.subtitles.setStyleSheet(config.style_subs)

    self.subtitles_vbox = QVBoxLayout(self.subtitles)
    self.subtitles_vbox.setSpacing(config.subs_padding_between_lines)
    self.subtitles_vbox.setContentsMargins(0, 0, 0, 0)

  def subtitles_base2(self):
    self.subtitles2 = QFrame()
    self.subtitles2.setAttribute(Qt.WA_TranslucentBackground)
    self.subtitles2.setWindowFlags(Qt.X11BypassWindowManagerHint)
    self.subtitles2.setStyleSheet(config.style_subs)

    self.subtitles_vbox2 = QVBoxLayout(self.subtitles2)
    self.subtitles_vbox2.setSpacing(config.subs_padding_between_lines)
    self.subtitles_vbox2.setContentsMargins(0, 0, 0, 0)

    if config.pause_during_translation_B:
      self.subtitles2.enterEvent = lambda event : [pause_on_popup(), setattr(config, 'block_popup', False)][0]
      self.subtitles2.leaveEvent = lambda event : [resume_on_popup(), setattr(config, 'block_popup', True)][0] if not config.avoid_resuming else [setattr(config, 'avoid_resuming', False), setattr(config, 'block_popup', True)][0]

  def popup_base(self):
    self.popup = QFrame()
    self.popup.setWindowFlags(Qt.X11BypassWindowManagerHint)
    self.popup.setStyleSheet(config.style_popup)

    self.popup_inner = QFrame()
    outer_box = QVBoxLayout(self.popup)
    outer_box.addWidget(self.popup_inner)

    self.popup_vbox = QVBoxLayout(self.popup_inner)
    self.popup_vbox.setSpacing(0)

  def render_subtitles(self, hide = False, redraw = False):
    if hide or not len(subs):
      try:
        self.subtitles.hide()
        self.subtitles2.hide()
      finally:
        return

    if redraw:
      self.subtitles.setStyleSheet(config.style_subs)
      self.subtitles2.setStyleSheet(config.style_subs)
    else:
      self.clearLayout('subs')
      self.clearLayout('subs2')

      if hasattr(self, 'popup'):
        self.popup.hide()

      # if subtitle consists of one overly long line - split into two
      if config.split_long_lines_B and len(subs.split('\n')) == 1 and len(subs.split(' ')) > config.split_long_lines_words_min - 1:
        subs2 = split_long_lines(subs)
      elif config.split_long_lines_B and len(subs) > config.split_long_lines_chars_min - 1:
        subs2 = split_long_lines(subs, config.split_long_lines_chars_min)
      else:
        subs2 = subs

      subs2 = re.sub(' +', ' ', subs2).strip()

      ##############################

      for line in subs2.split('\n'):
        line2 = ' %s ' % line.strip()
        ll = drawing_layer(line2, subs2)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addStretch()
        hbox.addWidget(ll)
        hbox.addStretch()
        self.subtitles_vbox.addLayout(hbox)

        ####################################

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)
        hbox.addStretch()

        line2 += '\00'

        # Japanese Fix
        mode = tokenizer.Tokenizer.SplitMode.C
        tokens = tokenizer_obj.tokenize(line2, mode)
        line2 = [m.surface() for m in tokens]
        readings = [m.reading_form() for m in tokens]

        for i in range(len(line2)):
          smbl = line2[i]
          word = smbl
          if smbl.isalpha():
            ll = events_class(word, subs2, reading=katakana_to_hiragana(readings[i]))
            ll.mouseHover.connect(self.render_popup)
            ll.redraw.connect(self.render_subtitles)

            hbox.addWidget(ll)
          else:
            ll = events_class(smbl, subs2, skip = True)
            hbox.addWidget(ll)

        hbox.addStretch()
        self.subtitles_vbox2.addLayout(hbox)

    self.subtitles.adjustSize()
    self.subtitles2.adjustSize()

    w = self.subtitles.geometry().width()
    h = self.subtitles.height = self.subtitles.geometry().height()

    x = (config.screen_width/2) - (w/2) + config.screen_start

    if config.subs_top_placement_B:
      y = config.subs_screen_edge_padding
    else:
      y = config.screen_height - config.subs_screen_edge_padding - h

    self.subtitles.setGeometry(int(x), int(y), 0, 0)
    self.subtitles.show()

    self.subtitles2.setGeometry(int(x), int(y), 0, 0)
    self.subtitles2.show()


  class TranslationThread(QThread):
    translation_done = pyqtSignal(str, bool, list)

    def __init__(self, text, is_line, parent=None):
      super().__init__(parent)
      self.text = text
      self.is_line = is_line

    def run(self):
      if self.is_line:
        line = globals()[config.translation_function_name_full_sentence](self.text)
        if config.translation_function_name_full_sentence == 'google':
          try:
            line = line[0][0][0].strip()
          except:
            line = 'Google translation failed.'
            if config.split_long_lines_B and len(line.split('\n')) == 1 and len(line.split(' ')) > config.split_long_lines_words_min - 1:
              line = split_long_lines(line)
            self.translation_done.emit(line, True, [])
      else:
        word = self.text
        translations = []
        for translation_function_name in config.translation_function_names:
          pairs, word_descr = globals()[translation_function_name](word)
          if not pairs:
            pairs = [['', '[Not found]']]
          translations.append((pairs, word_descr))
          self.translation_done.emit(word, False, translations)

  def render_popup(self, text, x_cursor_pos, is_line):
    global tthread
    global app
    global current_text
    if len(current_text) and text == current_text and hasattr(self, 'popup') and self.popup.isVisible():
      return
    if text == '':
      if hasattr(self, 'popup'):
        self.popup.hide()
      return

    current_text = text
    QApplication.setOverrideCursor(Qt.WaitCursor)

    def update_popup(result, is_line, data):
      self.clearLayout('popup')
      word = text
      if is_line:
        ll = QLabel(result)
        ll.setObjectName("first_line")
        self.popup_vbox.addWidget(ll)
      else:
        for translation_function_name_i, (pairs, word_descr) in enumerate(data):
          for i1, pair in enumerate(pairs[:config.number_of_translations]):
            if type(pair) == type(''):
              continue
            if config.split_long_lines_in_popup_B:
              pair[0] = split_long_lines(pair[0], max_symbols_per_line = config.split_long_lines_in_popup_symbols_min)
              pair[1] = split_long_lines(pair[1], max_symbols_per_line = config.split_long_lines_in_popup_symbols_min)

            if pair[0] == '-':
              pair[0] = ''
            if pair[1] == '-':
              pair[1] = ''

            if pair[0] != '':
              # to emphasize the exact form of the word
              # to ignore case on input and match it on output
              chnks = re.split(word, pair[0], flags = re.I)
              exct_words = re.findall(word, pair[0], flags = re.I)

              hbox = QHBoxLayout()
              hbox.setContentsMargins(0, 0, 0, 0)

              for i2, chnk in enumerate(chnks):
                if len(chnk):
                  ll = QLabel(chnk)
                  ll.setObjectName("first_line")
                  hbox.addWidget(ll)
                if i2 + 1 < len(chnks):
                  ll = QLabel(exct_words[i2])
                  ll.setObjectName("first_line_emphasize_word")
                  hbox.addWidget(ll)

              # filling the rest of the line with empty bg
              ll = QLabel()
              ll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
              hbox.addWidget(ll)

              self.popup_vbox.addLayout(hbox)

            if pair[1] != '':
              ll = QLabel(pair[1])
              ll.setObjectName("second_line")
              self.popup_vbox.addWidget(ll)

              # padding
              ll = QLabel()
              ll.setStyleSheet("font-size: 6px;")
              self.popup_vbox.addWidget(ll)

          if len(word_descr[0]):
            ll = QLabel(word_descr[0])
            ll.setProperty("morphology", word_descr[1])
            ll.setAlignment(Qt.AlignRight)
            self.popup_vbox.addWidget(ll)

          # delimiter between dictionaries
          if translation_function_name_i + 1 < len(config.translation_function_names):
            ll = QLabel()
            ll.setObjectName("delimiter")
            self.popup_vbox.addWidget(ll)

        app.sendPostedEvents()

        self.popup_inner.adjustSize()
        self.popup.adjustSize()

        w = self.popup.geometry().width()
        h = self.popup.geometry().height()

        if w > config.screen_width:
          w = config.screen_width - 20

        if x_cursor_pos == -1:
          x = config.screen_start + (config.screen_width/2) - (w/2)
        else:
          x = x_cursor_pos - w/2
          if x+w - config.screen_start > config.screen_width:
            x = config.screen_start + config.screen_width - w

        if config.subs_top_placement_B:
          y = self.subtitles.height + config.subs_screen_edge_padding
        else:
          y = config.screen_height - config.subs_screen_edge_padding - self.subtitles.height - h - 20

        self.popup.setGeometry(int(x), int(y), int(w), int(0))
        # without this the window flickers for a split second over the subtitles
        # causing it to get stuck in a loop of opening and closing the popup
        app.sendPostedEvents()
        self.popup.show()
        QApplication.restoreOverrideCursor()


    tthread = self.TranslationThread(text, is_line)
    tthread.translation_done.connect(update_popup)
    tthread.start()

def update_screen():
  if not mpv_fullscreen_status():
    mpv_id = subprocess.getoutput('xdotool search --class mpv')
    process_output = subprocess.getoutput('xdotool getwindowgeometry ' + mpv_id)
    if 'invalid' in process_output:
      return
    pos = re.search(r"Position:\s*(\d+),(\d+)", process_output)
    size = re.search(r"Geometry:\s*(\d+)x(\d+)", process_output)
    x = 0
    y = 0
    if pos:
      x, y = map(int, pos.groups())
    if size:
      w, h = map(int, size.groups())

    if 'x' in locals():
      config.screen_start = x
    elif not config.screen_start:
      config.screen_start = 0;
    if 'y' in locals() and 'h' in locals():
      config.screen_height = y + h
    elif not config.screen_height:
      config.screen_height = app.primaryScreen().geometry().height()
    if 'w' in locals():
      config.screen_width = w
    elif not config.screen_width:
      config.screen_width = app.primaryScreen().geometry().width()
  else:
    config.screen_start = app.primaryScreen().geometry().topLeft().x()
    config.screen_width = app.primaryScreen().size().width()
    config.screen_height = app.primaryScreen().size().height()

  form.obj.update_subtitles.emit(False, True)

if __name__ == "__main__":
  print('[py part] Starting jaSubs ...')

  try:
    os.mkdir('urls')
  except:
    pass

  if 'tab_divided_dict' in config.translation_function_names:
    offdict = { x.split('\t')[0].strip().lower() : x.split('\t')[1].strip() for x in open(os.path.expanduser(config.tab_divided_dict_fname)).readlines() if '\t' in x }

  mpv_socket = sys.argv[1]
  sub_file = sys.argv[2]
  # sub_file = '/tmp/mpv_sub_'
  # mpv_socket = '/tmp/mpv_socket_'

  subs = ''

  app = QApplication(sys.argv)

  config.avoid_resuming = False
  config.block_popup = False
  config.scroll = {}
  config.queue_to_translate = queue.Queue()

  form = main_class()
  update_screen()
  app.exec_()
