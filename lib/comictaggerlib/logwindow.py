"""
A PyQT4 dialog to a text file or log
"""

"""
Copyright 2012-2014  Anthony Beville

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

	http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import sys
from PyQt4 import QtCore, QtGui, uic
import os
from settings import ComicTaggerSettings


class LogWindow(QtGui.QDialog):
	
	
	def __init__(self, parent):
		super(LogWindow, self).__init__(parent)
		
		uic.loadUi(ComicTaggerSettings.getUIFile('logwindow.ui' ), self)
		
		self.setWindowFlags(self.windowFlags() |
									  QtCore.Qt.WindowSystemMenuHint |
									  QtCore.Qt.WindowMaximizeButtonHint)

	def setText( self, text ):
		self.textEdit.setPlainText( text ) 