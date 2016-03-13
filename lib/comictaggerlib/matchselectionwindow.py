"""
A PyQT4 dialog to select from automated issue matches
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
import os
from PyQt4 import QtCore, QtGui, uic

from PyQt4.QtCore import QUrl, pyqtSignal, QByteArray

from imagefetcher import  ImageFetcher
from settings import ComicTaggerSettings
from comicarchive import MetaDataStyle
from coverimagewidget import CoverImageWidget
from comicvinetalker import ComicVineTalker
import utils

class MatchSelectionWindow(QtGui.QDialog):
	
	volume_id = 0
	
	def __init__(self, parent, matches, comic_archive):
		super(MatchSelectionWindow, self).__init__(parent)
		
		uic.loadUi(ComicTaggerSettings.getUIFile('matchselectionwindow.ui' ), self)

		self.altCoverWidget = CoverImageWidget( self.altCoverContainer, CoverImageWidget.AltCoverMode )
		gridlayout = QtGui.QGridLayout( self.altCoverContainer )
		gridlayout.addWidget( self.altCoverWidget )
		gridlayout.setContentsMargins(0,0,0,0)

		self.archiveCoverWidget = CoverImageWidget( self.archiveCoverContainer, CoverImageWidget.ArchiveMode )
		gridlayout = QtGui.QGridLayout( self.archiveCoverContainer )
		gridlayout.addWidget( self.archiveCoverWidget )
		gridlayout.setContentsMargins(0,0,0,0)

		utils.reduceWidgetFontSize( self.twList )		
		utils.reduceWidgetFontSize( self.teDescription, 1 )

		self.setWindowFlags(self.windowFlags() |
									  QtCore.Qt.WindowSystemMenuHint |
									  QtCore.Qt.WindowMaximizeButtonHint)		

		self.matches = matches
		self.comic_archive = comic_archive
		
		self.twList.currentItemChanged.connect(self.currentItemChanged)	
		self.twList.cellDoubleClicked.connect(self.cellDoubleClicked)

		self.updateData()		

	def updateData( self):
			
		self.setCoverImage()
		self.populateTable()
		self.twList.resizeColumnsToContents()	
		self.twList.selectRow( 0 )
		
		path = self.comic_archive.path
		self.setWindowTitle( u"Select correct match: {0}".format(
						os.path.split(path)[1] ))
		
	def populateTable( self  ):

		while self.twList.rowCount() > 0:
			self.twList.removeRow(0)
		
		self.twList.setSortingEnabled(False)

		row = 0
		for match in self.matches: 
			self.twList.insertRow(row)
			
			item_text = match['series']  
			item = QtGui.QTableWidgetItem(item_text)			
			item.setData( QtCore.Qt.ToolTipRole, item_text )
			item.setData( QtCore.Qt.UserRole, (match,))
			item.setFlags(QtCore.Qt.ItemIsSelectable| QtCore.Qt.ItemIsEnabled)
			self.twList.setItem(row, 0, item)

			if match['publisher'] is not None:
				item_text = u"{0}".format(match['publisher'])
			else:
				item_text = u"Unknown"
			item = QtGui.QTableWidgetItem(item_text)
			item.setData( QtCore.Qt.ToolTipRole, item_text )
			item.setFlags(QtCore.Qt.ItemIsSelectable| QtCore.Qt.ItemIsEnabled)
			self.twList.setItem(row, 1, item)
			
			month_str = u""
			year_str = u"????"
			if match['month'] is not None:
				month_str = u"-{0:02d}".format(int(match['month']))
			if match['year'] is not None:
				year_str = u"{0}".format(match['year'])

			item_text = year_str + month_str			
			item = QtGui.QTableWidgetItem(item_text)			
			item.setData( QtCore.Qt.ToolTipRole, item_text )
			item.setFlags(QtCore.Qt.ItemIsSelectable| QtCore.Qt.ItemIsEnabled)
			self.twList.setItem(row, 2, item)

			item_text = match['issue_title']  
			if item_text is None:
				item_text = ""
			item = QtGui.QTableWidgetItem(item_text)			
			item.setData( QtCore.Qt.ToolTipRole, item_text )
			item.setFlags(QtCore.Qt.ItemIsSelectable| QtCore.Qt.ItemIsEnabled)
			self.twList.setItem(row, 3, item)
			
			row += 1

		self.twList.resizeColumnsToContents()
		self.twList.setSortingEnabled(True)
		self.twList.sortItems( 2 , QtCore.Qt.AscendingOrder )
		self.twList.selectRow(0)
		self.twList.resizeColumnsToContents()
		self.twList.horizontalHeader().setStretchLastSection(True) 
			

	def cellDoubleClicked( self, r, c ):
		self.accept()
			
	def currentItemChanged( self, curr, prev ):

		if curr is None:
			return
		if prev is not None and prev.row() == curr.row():
				return
		
		self.altCoverWidget.setIssueID( self.currentMatch()['issue_id'] )
		if self.currentMatch()['description'] is None:
			self.teDescription.setText ( "" )
		else:	
			self.teDescription.setText ( self.currentMatch()['description'] )
			
	def setCoverImage( self ):
		self.archiveCoverWidget.setArchive( self.comic_archive)

	def currentMatch( self ):
		row = self.twList.currentRow()
		match = self.twList.item(row, 0).data( QtCore.Qt.UserRole ).toPyObject()[0]
		return match

