#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.

import time
import datetime
from xml.dom.minidom import parseString
import urllib2
import shlex
import re
import os
import itertools

import mylar
from mylar import db, logger, helpers, filechecker

def dbUpdate(ComicIDList=None, calledfrom=None):

    myDB = db.DBConnection()
    #print "comicidlist:" + str(ComicIDList)
    if ComicIDList is None:
        if mylar.UPDATE_ENDED:
            logger.info('Updating only Continuing Series (option enabled) - this might cause problems with the pull-list matching for rebooted series')
            comiclist = []
            completelist = myDB.select('SELECT LatestDate, ComicPublished, ForceContinuing, NewPublish, LastUpdated, ComicID, ComicName from comics WHERE Status="Active" or Status="Loading" order by LatestDate DESC, LastUpdated ASC')
            for comlist in completelist:
                if comlist['LatestDate'] is None:
                    recentstatus = 'Loading'
                elif comlist['ComicPublished'] is None or comlist['ComicPublished'] == '' or comlist['LatestDate'] is None:
                    recentstatus = 'Unknown'
                elif comlist['ForceContinuing'] == 1:
                    recentstatus = 'Continuing'
                elif 'present' in comlist['ComicPublished'].lower() or (helpers.today()[:4] in comlist['LatestDate']):
                    latestdate = comlist['LatestDate']
                    c_date = datetime.date(int(latestdate[:4]), int(latestdate[5:7]), 1)
                    n_date = datetime.date.today()
                    recentchk = (n_date - c_date).days
                    if comlist['NewPublish']:
                        recentstatus = 'Continuing'
                    else:
                        if recentchk < 55:
                            recentstatus = 'Continuing'
                        else:
                            recentstatus = 'Ended'
                else:
                    recentstatus = 'Ended'

                if recentstatus == 'Continuing':
                    comiclist.append({"LatestDate":    comlist['LatestDate'],
                                      "LastUpdated":   comlist['LastUpdated'],
                                      "ComicID":       comlist['ComicID'],
                                      "ComicName":     comlist['ComicName']})

        else:
            comiclist = myDB.select('SELECT LatestDate, LastUpdated, ComicID, ComicName from comics WHERE Status="Active" or Status="Loading" order by LatestDate DESC, LastUpdated ASC')
    else:
        comiclist = ComicIDList

    if calledfrom is None:
        logger.info('Starting update for %i active comics' % len(comiclist))

    cnt = 1

    for comic in comiclist:
        if ComicIDList is None:
            ComicID = comic['ComicID']
            ComicName = comic['ComicName']
            c_date = comic['LastUpdated']
            if c_date is None:
                logger.error(ComicName + ' failed during a previous add /refresh as it has no Last Update timestamp. Forcing refresh now.')
            else:
                c_obj_date = datetime.datetime.strptime(c_date, "%Y-%m-%d %H:%M:%S")
                n_date = datetime.datetime.now()
                absdiff = abs(n_date - c_obj_date)
                hours = (absdiff.days * 24 * 60 * 60 + absdiff.seconds) / 3600.0
                if hours < 5:
                    logger.info(ComicName + '[' + str(ComicID) + '] Was refreshed less than 5 hours ago. Skipping Refresh at this time.')
                    cnt +=1
                    continue
            logger.info('[' + str(cnt) + '/' + str(len(comiclist)) + '] Refreshing :' + ComicName + ' [' + str(ComicID) + ']')
        else:
            ComicID = comic
            logger.fdebug('Refreshing :' + str(ComicID))
        mismatch = "no"
        if not mylar.CV_ONLY or ComicID[:1] == "G":

            CV_EXcomicid = myDB.selectone("SELECT * from exceptions WHERE ComicID=?", [ComicID]).fetchone()
            if CV_EXcomicid is None: pass
            else:
                if CV_EXcomicid['variloop'] == '99':
                    mismatch = "yes"
            if ComicID[:1] == "G":
                mylar.importer.GCDimport(ComicID)
            else:
                cchk = importer.addComictoDB(ComicID, mismatch)
                if cchk == 'apireached':
                    logger.warn('API Limit has been reached. Aborting update at this time.')
                    return
        else:
            if mylar.CV_ONETIMER == 1:
                logger.fdebug("CV_OneTimer option enabled...")
                #in order to update to JUST CV_ONLY, we need to delete the issues for a given series so it's a clea$
                logger.fdebug("Gathering the status of all issues for the series.")
                issues = myDB.select('SELECT * FROM issues WHERE ComicID=?', [ComicID])

                if not issues:
                    #if issues are None it's probably a bad refresh/maxed out API that resulted in the issue data
                    #getting wiped out and not refreshed. Setting whack=True will force a complete refresh.
                    logger.fdebug('No issue data available. This is Whack.')
                    whack = True
                else:
                    #check for series that are numerically out of whack (ie. 5/4)
                    logger.fdebug('Checking how out of whack the series is.')
                    whack = helpers.havetotals(refreshit=ComicID)

                if calledfrom == 'weekly':
                    if whack == True:
                        logger.info('Series is out of whack. Forcibly refreshing series to ensure everything is in order.')
                        return True
                    else:
                        return False

                annload = []  #initiate the list here so we don't error out below.

                if mylar.ANNUALS_ON:
                    #now we load the annuals into memory to pass through to importer when refreshing so that it can
                    #refresh even the manually added annuals.
                    annual_load = myDB.select('SELECT * FROM annuals WHERE ComicID=?', [ComicID])
                    logger.fdebug('checking annual db')
                    for annthis in annual_load:
                        if not any(d['ReleaseComicID'] == annthis['ReleaseComicID'] for d in annload):
                            #print 'matched on annual'
                            annload.append({
                                  'ReleaseComicID':   annthis['ReleaseComicID'],
                                  'ReleaseComicName': annthis['ReleaseComicName'],
                                  'ComicID':          annthis['ComicID'],
                                  'ComicName':        annthis['ComicName']
                                  })
                            #print 'added annual'
                    issues += annual_load #myDB.select('SELECT * FROM annuals WHERE ComicID=?', [ComicID])
                #store the issues' status for a given comicid, after deleting and readding, flip the status back to$
                logger.fdebug("Deleting all issue data.")
                myDB.action('DELETE FROM issues WHERE ComicID=?', [ComicID])
                myDB.action('DELETE FROM annuals WHERE ComicID=?', [ComicID])
                logger.fdebug("Refreshing the series and pulling in new data using only CV.")

                if whack == False:
                    cchk = mylar.importer.addComictoDB(ComicID, mismatch, calledfrom='dbupdate', annload=annload)
                    if cchk == 'apireached':
                        logger.warn('API Limit has been reached. Aborting update at this time.')
                        break                    
                    #reload the annuals here.

                    issues_new = myDB.select('SELECT * FROM issues WHERE ComicID=?', [ComicID])
                    annuals = []
                    ann_list = []
                    if mylar.ANNUALS_ON:
                        annuals_list = myDB.select('SELECT * FROM annuals WHERE ComicID=?', [ComicID])
                        ann_list += annuals_list
                        issues_new += annuals_list

                    logger.fdebug("Attempting to put the Status' back how they were.")
                    icount = 0
                    #the problem - the loop below will not match on NEW issues that have been refreshed that weren't present in the
                    #db before (ie. you left Mylar off for abit, and when you started it up it pulled down new issue information)
                    #need to test if issuenew['Status'] is None, but in a seperate loop below.
                    fndissue = []
                    for issue in issues:
                        for issuenew in issues_new:
                            #logger.fdebug(str(issue['Issue_Number']) + ' - issuenew:' + str(issuenew['IssueID']) + ' : ' + str(issuenew['Status']))
                            #logger.fdebug(str(issue['Issue_Number']) + ' - issue:' + str(issue['IssueID']) + ' : ' + str(issue['Status']))
                            try:
                                if issuenew['IssueID'] == issue['IssueID'] and (issuenew['Status'] != issue['Status'] or issue['IssueDate_Edit'] is not None):
                                    ctrlVAL = {"IssueID":      issue['IssueID']}
                                    #if the status is None and the original status is either Downloaded / Archived, keep status & stats
                                    if issuenew['Status'] == None and (issue['Status'] == 'Downloaded' or issue['Status'] == 'Archived'):
                                        newVAL = {"Location":     issue['Location'],
                                                  "ComicSize":    issue['ComicSize'],
                                                  "Status":       issue['Status']}
                                    #if the status is now Downloaded/Snatched, keep status & stats (downloaded only)
                                    elif issuenew['Status'] == 'Downloaded' or issue['Status'] == 'Snatched':
                                        newVAL = {"Location":      issue['Location'],
                                                  "ComicSize":     issue['ComicSize']}
                                        if issuenew['Status'] == 'Downloaded':
                                            newVAL['Status'] = issuenew['Status']
                                        else:
                                            newVAL['Status'] = issue['Status']

                                    elif issue['Status'] == 'Archived':
                                        newVAL = {"Status":        issue['Status'],
                                                  "Location":      issue['Location'],
                                                  "ComicSize":     issue['ComicSize']}
                                    else:
                                        #change the status to the previous status
                                        newVAL = {"Status":        issue['Status']}

                                    if newVAL['Status'] == None:
                                        datechk = re.sub('-', '', newissue['ReleaseDate']).strip() # converts date to 20140718 format
                                        if mylar.AUTOWANT_ALL:
                                            newVAL = {"Status": "Wanted"}
                                        elif int(datechk) >= int(nowtime) and mylar.AUTOWANT_UPCOMING:
                                            newVAL = {"Status": "Wanted"}
                                        else:
                                            newVAL = {"Status":  "Skipped"}

                                    if issue['IssueDate_Edit']:
                                        logger.info('[#' + str(issue['Issue_Number']) + '] detected manually edited Issue Date.')
                                        logger.info('new value : ' + str(issue['IssueDate']) + ' ... cv value : ' + str(issuenew['IssueDate']))
                                        newVAL['IssueDate'] = issue['IssueDate']
                                        newVAL['IssueDate_Edit'] = issue['IssueDate_Edit']

                                    if any(d['IssueID'] == str(issue['IssueID']) for d in ann_list):
                                        #logger.fdebug("annual detected for " + str(issue['IssueID']) + " #: " + str(issue['Issue_Number']))
                                        myDB.upsert("Annuals", newVAL, ctrlVAL)
                                    else:
                                        #logger.fdebug('#' + str(issue['Issue_Number']) + ' writing issuedata: ' + str(newVAL))
                                        myDB.upsert("Issues", newVAL, ctrlVAL)
                                    fndissue.append({"IssueID":      issue['IssueID']})
                                    icount+=1
                                    break
                            except:
                                logger.warn('Something is out of whack somewhere with the series.')
                                #if it's an annual (ie. deadpool-2011 ) on a refresh will throw index errors for some reason.

                    logger.info("In the process of converting the data to CV, I changed the status of " + str(icount) + " issues.")

                    issuesnew = myDB.select('SELECT * FROM issues WHERE ComicID=? AND Status is NULL', [ComicID])

                    if mylar.AUTOWANT_UPCOMING:
                        newstatus = "Wanted"
                    else:
                        newstatus = "Skipped"

                    newiss = []

                    for iss in issuesnew:
                         newiss.append({"IssueID":      iss['IssueID'],
                                        "Status":       newstatus,
                                        "Annual":       False})

                    if mylar.ANNUALS_ON:
                        annualsnew = myDB.select('SELECT * FROM annuals WHERE ComicID=? AND Status is NULL', [ComicID])

                        for ann in annualsnew:
                             newiss.append({"IssueID":      iss['IssueID'],
                                            "Status":       newstatus,
                                            "Annual":       True})

                    if len(newiss) > 0:
                         for newi in newiss:
                             ctrlVAL = {"IssueID":   newi['IssueID']}
                             newVAL = {"Status":     newi['Status']}
                             #logger.fdebug('writing issuedata: ' + str(newVAL))
                             if newi['Annual'] == True:
                                 myDB.upsert("Annuals", newVAL, ctrlVAL)
                             else:
                                 myDB.upsert("Issues", newVAL, ctrlVAL)

                    logger.info('I have added ' + str(len(newiss)) + ' new issues for this series that were not present before.')
                    forceRescan(ComicID)

                else:
                    cchk = mylar.importer.addComictoDB(ComicID, mismatch, annload=annload)
                    if cchk == 'apireached':
                        logger.warn('API Limit has been reached. Aborting update at this time.')
                        break

            else:
                cchk = mylar.importer.addComictoDB(ComicID, mismatch)
                if cchk == 'apireached':
                    logger.warn('API Limit has been reached. Aborting update at this time.')
                    break

        cnt +=1
        time.sleep(15) #pause for 15 secs so dont hammer CV and get 500 error
    logger.info('Update complete')


def latest_update(ComicID, LatestIssue, LatestDate):
    # here we add to comics.latest
    #logger.info(str(ComicID) + ' - updating latest_date to : ' + str(LatestDate))
    myDB = db.DBConnection()
    latestCTRLValueDict = {"ComicID":      ComicID}
    newlatestDict = {"LatestIssue":      str(LatestIssue),
                    "LatestDate":       str(LatestDate)}
    myDB.upsert("comics", newlatestDict, latestCTRLValueDict)

def upcoming_update(ComicID, ComicName, IssueNumber, IssueDate, forcecheck=None, futurepull=None, altissuenumber=None):
    # here we add to upcoming table...
    myDB = db.DBConnection()
    dspComicName = ComicName #to make sure that the word 'annual' will be displayed on screen
    if 'annual' in ComicName.lower():
        adjComicName = re.sub("\\bannual\\b", "", ComicName.lower()) # for use with comparisons.
        logger.fdebug('annual detected - adjusting name to : ' + adjComicName)
    else:
        adjComicName = ComicName
    controlValue = {"ComicID":      ComicID}
    newValue = {"ComicName":        adjComicName,
                "IssueNumber":      str(IssueNumber),
                "DisplayComicName": dspComicName,
                "IssueDate":        str(IssueDate)}

    #let's refresh the series here just to make sure if an issue is available/not.
    mismatch = "no"
    CV_EXcomicid = myDB.selectone("SELECT * from exceptions WHERE ComicID=?", [ComicID]).fetchone()
    if CV_EXcomicid is None: pass
    else:
        if CV_EXcomicid['variloop'] == '99':
            mismatch = "yes"
    lastupdatechk = myDB.selectone("SELECT * FROM comics WHERE ComicID=?", [ComicID]).fetchone()
    if lastupdatechk is None:
        pullupd = "yes"
    else:
        c_date = lastupdatechk['LastUpdated']
        if c_date is None:
            logger.error(lastupdatechk['ComicName'] + ' failed during a previous add /refresh. Please either delete and readd the series, or try a refresh of the series.')
            return
        c_obj_date = datetime.datetime.strptime(c_date, "%Y-%m-%d %H:%M:%S")
        n_date = datetime.datetime.now()
        absdiff = abs(n_date - c_obj_date)
        hours = (absdiff.days * 24 * 60 * 60 + absdiff.seconds) / 3600.0
        # no need to hammer the refresh
        # let's check it every 5 hours (or more)
        #pullupd = "yes"
    if 'annual' in ComicName.lower():
        if mylar.ANNUALS_ON:
            issuechk = myDB.selectone("SELECT * FROM annuals WHERE ComicID=? AND Issue_Number=?", [ComicID, IssueNumber]).fetchone()
        else:
            logger.fdebug('Annual detected, but annuals not enabled. Ignoring result.')
            return
    else:
        issuechk = myDB.selectone("SELECT * FROM issues WHERE ComicID=? AND Issue_Number=?", [ComicID, IssueNumber]).fetchone()

    if issuechk is None and altissuenumber is not None:
        logger.info('altissuenumber is : ' + str(altissuenumber))
        issuechk = myDB.selectone("SELECT * FROM issues WHERE ComicID=? AND Int_IssueNumber=?", [ComicID, helpers.issuedigits(altissuenumber)]).fetchone()
    if issuechk is None:
        if futurepull is None:
            og_status = None
            logger.fdebug(adjComicName + ' Issue: ' + str(IssueNumber) + ' not present in listings to mark for download...updating comic and adding to Upcoming Wanted Releases.')
            # we need to either decrease the total issue count, OR indicate that an issue is upcoming.
            upco_results = myDB.select("SELECT COUNT(*) FROM UPCOMING WHERE ComicID=?", [ComicID])
            upco_iss = upco_results[0][0]
            #logger.info("upco_iss: " + str(upco_iss))
            if int(upco_iss) > 0:
                #logger.info("There is " + str(upco_iss) + " of " + str(ComicName) + " that's not accounted for")
                newKey = {"ComicID": ComicID}
                newVal = {"not_updated_db": str(upco_iss)}
                myDB.upsert("comics", newVal, newKey)
            elif int(upco_iss) <=0 and lastupdatechk['not_updated_db']:
               #if not_updated_db has a value, and upco_iss is > 0, let's zero it back out cause it's updated now.
                newKey = {"ComicID": ComicID}
                newVal = {"not_updated_db": ""}
                myDB.upsert("comics", newVal, newKey)

            if hours > 5 or forcecheck == 'yes':
                pullupd = "yes"
                logger.fdebug('Now Refreshing comic ' + ComicName + ' to make sure it is up-to-date')
                if ComicID[:1] == "G": 
                    mylar.importer.GCDimport(ComicID, pullupd)
                else: 
                    cchk = mylar.importer.updateissuedata(ComicID, ComicName, calledfrom='weeklycheck')#mylar.importer.addComictoDB(ComicID,mismatch,pullupd)
                    if cchk == 'apireached':
                        logger.warn('API Limit has been reached. Aborting update at this time.')
                        return
            else:
                logger.fdebug('It has not been longer than 5 hours since we last did this...we will wait so we do not hammer things.')
                logger.fdebug('linking ComicID to Pull-list to reflect status.')
                downstats = {"ComicID": ComicID,
                             "IssueID": None,
                             "Status": None}
                return downstats
        else:
            # if futurepull is not None, let's just update the status and ComicID
            # NOTE: THIS IS CREATING EMPTY ENTRIES IN THE FUTURE TABLE. ???
            nKey = {"ComicID": ComicID}
            nVal = {"Status": "Wanted"}
            myDB.upsert("future", nVal, nKey)
            return

    if issuechk is not None:
        if issuechk['Issue_Number'] == IssueNumber or issuechk['Issue_Number'] == altissuenumber:
            og_status = issuechk['Status']
            #check for 'out-of-whack' series here.
            whackness = dbUpdate([ComicID], calledfrom='weekly')
            if whackness == True:
                if any([issuechk['Status'] == 'Downloaded', issuechk['Status'] == 'Archived', issuechk['Status'] == 'Snatched']):
                    logger.fdebug('Forcibly maintaining status of : ' + og_status + ' for #' + issuechk['Issue_Number'] + ' to ensure integrity.')
                logger.fdebug('Comic series has an incorrect total count. Forcily refreshing series to ensure data is current.')
                dbUpdate([ComicID])
                issuechk = myDB.selectone("SELECT * FROM issues WHERE ComicID=? AND Int_IssueNumber=?", [ComicID, helpers.issuedigits(IssueNumber)]).fetchone()
                if issuechk['Status'] != og_status and (issuechk['Status'] != 'Downloaded' or issuechk['Status'] != 'Archived' or issuechk['Status'] != 'Snatched'):
                    logger.fdebug('Forcibly changing status of ' + issuechk['Status'] + ' back to ' + og_status + ' for #' + issuechk['Issue_Number'] + ' to stop repeated downloads.')
                else:
                    logger.fdebug('[' + issuechk['Status'] + '] / [' + og_status + '] Status has not changed during refresh or is marked as being Wanted/Skipped correctly.')
                    og_status = issuechk['Status']
            else:
                logger.fdebug('Comic series already up-to-date ... no need to refresh at this time.')

            logger.fdebug('Available to be marked for download - checking...' + adjComicName + ' Issue: ' + str(issuechk['Issue_Number']))
            logger.fdebug('...Existing status: ' + og_status)
            control = {"IssueID":   issuechk['IssueID']}
            newValue['IssueID'] = issuechk['IssueID']
            if og_status == "Snatched":
                values = {"Status":   "Snatched"}
                newValue['Status'] = "Snatched"
            elif og_status == "Downloaded":
                values = {"Status":    "Downloaded"}
                newValue['Status'] = "Downloaded"
                #if the status is Downloaded and it's on the pullist - let's mark it so everyone can bask in the glory

            elif og_status == "Wanted":
                values = {"Status":    "Wanted"}
                newValue['Status'] = "Wanted"
            elif og_status == "Archived":
                values = {"Status":    "Archived"}
                newValue['Status'] = "Archived"
            elif og_status == 'Failed':
                if mylar.FAILED_DOWNLOAD_HANDLING:
                    if mylar.FAILED_AUTO:
                        values = {"Status":   "Wanted"}
                        newValue['Status'] = "Wanted"
                    else:
                        values = {"Status":   "Failed"}
                        newValue['Status'] = "Failed"
                else:
                    values = {"Status":   "Skipped"}
                    newValue['Status'] = "Skipped"
            else:
                values = {"Status":    "Skipped"}
                newValue['Status'] = "Skipped"
            #was in wrong place :(
        else:
            logger.fdebug('Issues do not match for some reason...weekly new issue: ' + str(IssueNumber))
            return

    if mylar.AUTOWANT_UPCOMING:
        #for issues not in db - to be added to Upcoming table.
        if og_status is None:
            newValue['Status'] = "Wanted"
            logger.fdebug('...Changing Status to Wanted and throwing it in the Upcoming section since it is not published yet.')
        #this works for issues existing in DB...
        elif og_status == "Skipped":
            newValue['Status'] = "Wanted"
            values = {"Status":  "Wanted"}
            logger.fdebug('...New status of Wanted')
        elif og_status == "Wanted":
            logger.fdebug('...Status already Wanted .. not changing.')
        else:
            logger.fdebug('...Already have issue - keeping existing status of : ' + og_status)

    if issuechk is None:
        myDB.upsert("upcoming", newValue, controlValue)
        logger.fdebug('updating Pull-list to reflect status.')
        downstats = {"Status":  newValue['Status'],
                     "ComicID": ComicID,
                     "IssueID": None}
        return downstats

    else:
        logger.fdebug('--attempt to find errant adds to Wanted list')
        logger.fdebug('UpcomingNewValue: ' + str(newValue))
        logger.fdebug('UpcomingcontrolValue: ' + str(controlValue))
        if issuechk['IssueDate'] == '0000-00-00' and newValue['IssueDate'] != '0000-00-00':
            logger.fdebug('Found a 0000-00-00 issue - force updating series to try and get it proper.')
            dateVal = {"IssueDate":        newValue['IssueDate'],
                       "ComicName":        issuechk['ComicName'],
                       "Status":           newValue['Status'],
                       "IssueNumber":      issuechk['Issue_Number']}
            logger.fdebug('updating date in upcoming table to : ' + str(newValue['IssueDate']) + '[' + newValue['Status'] + ']')
            logger.fdebug('ComicID:' + str(controlValue))
            myDB.upsert("upcoming", dateVal, controlValue)
            logger.fdebug('Temporarily putting the Issue Date for ' + str(issuechk['Issue_Number']) + ' to ' + str(newValue['IssueDate']))
            values = {"IssueDate":  newValue['IssueDate']}
            #if ComicID[:1] == "G": mylar.importer.GCDimport(ComicID,pullupd='yes')
            #else: mylar.importer.addComictoDB(ComicID,mismatch,pullupd='yes')

        if 'annual' in ComicName.lower():
            myDB.upsert("annuals", values, control)
        else:
            myDB.upsert("issues", values, control)

        if any([og_status == 'Downloaded', og_status == 'Archived', og_status == 'Snatched', og_status == 'Wanted', newValue['Status'] == 'Wanted']):
            logger.fdebug('updating Pull-list to reflect status change: ' + og_status + '[' + newValue['Status'] + ']')
            if og_status != 'Skipped':
                downstats = {"Status":  og_status,
                             "ComicID": issuechk['ComicID'],
                             "IssueID": issuechk['IssueID']}
            else:
                downstats = {"Status":  newValue['Status'],
                             "ComicID": issuechk['ComicID'],
                             "IssueID": issuechk['IssueID']}
            return downstats


def weekly_update(ComicName, IssueNumber, CStatus, CID, futurepull=None, altissuenumber=None):
    if futurepull:
        logger.fdebug('future_update of table : ' + str(ComicName) + ' #:' + str(IssueNumber) + ' to a status of ' + str(CStatus))
    else:
        logger.fdebug('weekly_update of table : ' + str(ComicName) + ' #:' + str(IssueNumber) + ' to a status of ' + str(CStatus))

    if altissuenumber:
        logger.fdebug('weekly_update of table : ' + str(ComicName) + ' (Alternate Issue #):' + str(altissuenumber) + ' to a status of ' + str(CStatus))

    # here we update status of weekly table...
    # added Issue to stop false hits on series' that have multiple releases in a week
    # added CStatus to update status flags on Pullist screen
    myDB = db.DBConnection()
    if futurepull is None:
        issuecheck = myDB.selectone("SELECT * FROM weekly WHERE COMIC=? AND ISSUE=?", [ComicName, IssueNumber]).fetchone()
    else:
        issuecheck = myDB.selectone("SELECT * FROM future WHERE COMIC=? AND ISSUE=?", [ComicName, IssueNumber]).fetchone()
    if issuecheck is not None:
        controlValue = {"COMIC":         str(ComicName),
                         "ISSUE":         str(IssueNumber)}

        try:
            if CID['IssueID']:
                cidissueid = CID['IssueID']
            else:
                cidissueid = None
        except:
            cidissueid = None

        if CStatus:
            newValue = {"STATUS":      CStatus}

        else:
            if mylar.AUTOWANT_UPCOMING:
                newValue = {"STATUS":      "Wanted"}
            else:
                newValue = {"STATUS":      "Skipped"}

        #setting this here regardless, as it will be a match for a watchlist hit at this point anyways - so link it here what's availalbe.
        newValue['ComicID'] = CID['ComicID']
        newValue['IssueID'] = cidissueid

        if futurepull is None:
            myDB.upsert("weekly", newValue, controlValue)
        else:
            logger.fdebug('checking ' + str(issuecheck['ComicID']) + ' status of : ' + str(CStatus))
            if issuecheck['ComicID'] is not None and CStatus != None:
                newValue = {"STATUS":       "Wanted",
                            "ComicID":      issuecheck['ComicID']}
            logger.fdebug('updating value: ' + str(newValue))
            logger.fdebug('updating control: ' + str(controlValue))
            myDB.upsert("future", newValue, controlValue)

def newpullcheck(ComicName, ComicID, issue=None):
    # When adding a new comic, let's check for new issues on this week's pullist and update.
    mylar.weeklypull.pullitcheck(comic1off_name=ComicName, comic1off_id=ComicID, issue=issue)
    return

def no_searchresults(ComicID):
    # when there's a mismatch between CV & GCD - let's change the status to
    # something other than 'Loaded'
    myDB = db.DBConnection()
    controlValue = {"ComicID":        ComicID}
    newValue = {"Status":       "Error",
                "LatestDate":   "Error",
                "LatestIssue":  "Error"}
    myDB.upsert("comics", newValue, controlValue)

def nzblog(IssueID, NZBName, ComicName, SARC=None, IssueArcID=None, id=None, prov=None, alt_nzbname=None):
    myDB = db.DBConnection()

    newValue = {'NZBName':  NZBName}

    if SARC:
       IssueID = 'S' + str(IssueArcID)
       newValue['SARC'] = SARC

    if IssueID is None or IssueID == 'None':
       #if IssueID is None, it's a one-off download from the pull-list.
       #give it a generic ID above the last one so it doesn't throw an error later.
       logger.fdebug("Story Arc (SARC) detected as: " + str(SARC))
       if mylar.HIGHCOUNT == 0:
           IssueID = '900000'
       else:
           IssueID = int(mylar.HIGHCOUNT) + 1

    controlValue = {"IssueID":  IssueID,
                    "Provider": prov}


    if id:
        logger.info('setting the nzbid for this download grabbed by ' + prov + ' in the nzblog to : ' + str(id))
        newValue['ID'] = id

    if alt_nzbname:
        logger.info('setting the alternate nzbname for this download grabbed by ' + prov + ' in the nzblog to : ' + alt_nzbname)
        newValue['AltNZBName'] = alt_nzbname

    #check if it exists already in the log.
    chkd = myDB.selectone('SELECT * FROM nzblog WHERE IssueID=? and Provider=?', [IssueID, prov]).fetchone()
    if chkd is None:
        pass
    else:
        if chkd['AltNZBName'] is None or chkd['AltNZBName'] == '':
            #we need to wipe the entry so we can re-update with the alt-nzbname if required
            myDB.action('DELETE FROM nzblog WHERE IssueID=? and Provider=?', [IssueID, prov])
            logger.fdebug('Deleted stale entry from nzblog for IssueID: ' + str(IssueID) + ' [' + prov + ']')
    myDB.upsert("nzblog", newValue, controlValue)


def foundsearch(ComicID, IssueID, mode=None, down=None, provider=None, SARC=None, IssueArcID=None, module=None):
    # When doing a Force Search (Wanted tab), the resulting search calls this to update.

    # this is all redudant code that forceRescan already does.
    # should be redone at some point so that instead of rescanning entire
    # series directory, it just scans for the issue it just downloaded and
    # and change the status to Snatched accordingly. It is not to increment the have count
    # at this stage as it's not downloaded - just the .nzb has been snatched and sent to SAB.
    if module is None:
        module = ''
    module += '[UPDATER]'

    myDB = db.DBConnection()
    modcomicname = False

    logger.fdebug(module + ' comicid: ' + str(ComicID))
    logger.fdebug(module + ' issueid: ' + str(IssueID))
    if mode != 'story_arc':
        comic = myDB.selectone('SELECT * FROM comics WHERE ComicID=?', [ComicID]).fetchone()
        ComicName = comic['ComicName']
        if mode == 'want_ann':
            issue = myDB.selectone('SELECT * FROM annuals WHERE IssueID=?', [IssueID]).fetchone()
            if ComicName != issue['ReleaseComicName'] + ' Annual':
                ComicName = issue['ReleaseComicName']
                modcomicname = True
        else:
            issue = myDB.selectone('SELECT * FROM issues WHERE IssueID=?', [IssueID]).fetchone()
        CYear = issue['IssueDate'][:4]

    else:
        issue = myDB.selectone('SELECT * FROM readinglist WHERE IssueArcID=?', [IssueArcID]).fetchone()
        ComicName = issue['ComicName']
        CYear = issue['IssueYEAR']

    if down is None:
        # update the status to Snatched (so it won't keep on re-downloading!)
        logger.info(module + ' Updating status to snatched')
        logger.fdebug(module + ' Provider is ' + provider)
        newValue = {"Status":    "Snatched"}
        if mode == 'story_arc':
            cValue = {"IssueArcID": IssueArcID}
            snatchedupdate = {"IssueArcID": IssueArcID}
            myDB.upsert("readinglist", newValue, cValue)
            # update the snatched DB
            snatchedupdate = {"IssueID":     IssueArcID,
                              "Status":      "Snatched",
                              "Provider":    provider
                              }

        else:
            if mode == 'want_ann':
                controlValue = {"IssueID":   IssueID}
                myDB.upsert("annuals", newValue, controlValue)
            else:
                controlValue = {"IssueID":   IssueID}
                myDB.upsert("issues", newValue, controlValue)

            # update the snatched DB
            snatchedupdate = {"IssueID":     IssueID,
                              "Status":      "Snatched",
                              "Provider":    provider
                              }

        if mode == 'story_arc':
            IssueNum = issue['IssueNumber']
            newsnatchValues = {"ComicName":       ComicName,
                               "ComicID":         'None',
                               "Issue_Number":    IssueNum,
                               "DateAdded":       helpers.now(),
                               "Status":          "Snatched"
                               }
        else:
            if modcomicname:
                IssueNum = issue['Issue_Number']
            else:
                if mode == 'want_ann':
                    IssueNum = "Annual " + issue['Issue_Number']
                else:
                    IssueNum = issue['Issue_Number']

            newsnatchValues = {"ComicName":       ComicName,
                               "ComicID":         ComicID,
                               "Issue_Number":    IssueNum,
                               "DateAdded":       helpers.now(),
                               "Status":          "Snatched"
                               }
        myDB.upsert("snatched", newsnatchValues, snatchedupdate)

        #this will update the weeklypull list immediately after sntaching to reflect the new status.
        #-is ugly, should be linked directly to other table (IssueID should be populated in weekly pull at this point hopefully).
        chkit = myDB.selectone("SELECT * FROM weekly WHERE ComicID=? AND IssueID=?", [ComicID, IssueID]).fetchone()

        if chkit is not None:

            ctlVal = {"ComicID":  ComicID,
                      "IssueID":  IssueID}
            newVal = {"Status":   "Snatched"}
            myDB.upsert("weekly", newVal, ctlVal)

        logger.info(module + ' Updated the status (Snatched) complete for ' + ComicName + ' Issue: ' + str(IssueNum))
    else:
        if down == 'PP':
            logger.info(module + ' Setting status to Post-Processed in history.')
            downstatus = 'Post-Processed'
        else:
            logger.info(module + ' Setting status to Downloaded in history.')
            downstatus = 'Downloaded'
        if mode == 'want_ann':
            if modcomicname:
                IssueNum = issue['Issue_Number']
            else:
                IssueNum = "Annual " + issue['Issue_Number']
        elif mode == 'story_arc':
            IssueNum = issue['IssueNumber']
            IssueID = IssueArcID
        else:
            IssueNum = issue['Issue_Number']

        snatchedupdate = {"IssueID":     IssueID,
                          "Status":      downstatus,
                          "Provider":    provider
                          }
        newsnatchValues = {"ComicName":       ComicName,
                           "ComicID":         ComicID,
                           "Issue_Number":    IssueNum,
                           "DateAdded":       helpers.now(),
                           "Status":          downstatus
                           }
        myDB.upsert("snatched", newsnatchValues, snatchedupdate)

        if mode == 'story_arc':
            cValue = {"IssueArcID":   IssueArcID}
            nValue = {"Status":       "Downloaded"}
            myDB.upsert("readinglist", nValue, cValue)

        else:
            controlValue = {"IssueID":   IssueID}
            newValue = {"Status":    "Downloaded"}
            if mode == 'want_ann':
                myDB.upsert("annuals", newValue, controlValue)
            else:
                myDB.upsert("issues", newValue, controlValue)

        #this will update the weeklypull list immediately after post-processing to reflect the new status.
        chkit = myDB.selectone("SELECT * FROM weekly WHERE ComicID=? AND IssueID=? AND Status='Snatched'", [ComicID, IssueID]).fetchone()

        if chkit is not None:

            ctlVal = {"ComicID":  ComicID,
                      "IssueID":  IssueID}
            newVal = {"Status":   "Downloaded"}
            myDB.upsert("weekly", newVal, ctlVal)

        logger.info(module + ' Updating Status (' + downstatus + ') now complete for ' + ComicName + ' issue: ' + IssueNum)
    return

def forceRescan(ComicID, archive=None, module=None):
    if module is None:
        module = ''
    module += '[FILE-RESCAN]'
    myDB = db.DBConnection()
    # file check to see if issue exists
    rescan = myDB.selectone('SELECT * FROM comics WHERE ComicID=?', [ComicID]).fetchone()
    if rescan['AlternateSearch'] is not None:
        altnames = rescan['AlternateSearch'] + '##'
    else:
        altnames = ''
    annscan = myDB.select('SELECT * FROM annuals WHERE ComicID=?', [ComicID])
    if annscan is None:
        pass
    else:
        for ascan in annscan:
            #logger.info('ReleaseComicName: ' + ascan['ReleaseComicName'])
            if ascan['ReleaseComicName'] not in altnames:
                altnames += ascan['ReleaseComicName'] + '!!' + ascan['ReleaseComicID'] + '##'
        altnames = altnames[:-2]
    logger.info(module + ' Now checking files for ' + rescan['ComicName'] + ' (' + str(rescan['ComicYear']) + ') in ' + rescan['ComicLocation'])
    fca = []
    if archive is None:
        tmpval = filechecker.listFiles(dir=rescan['ComicLocation'], watchcomic=rescan['ComicName'], Publisher=rescan['ComicPublisher'], AlternateSearch=altnames)
        comiccnt = int(tmpval['comiccount'])
        logger.fdebug(module + 'comiccnt is:' + str(comiccnt))
        fca.append(tmpval)
        if mylar.MULTIPLE_DEST_DIRS is not None and mylar.MULTIPLE_DEST_DIRS != 'None' and os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(rescan['ComicLocation'])) != rescan['ComicLocation']:
            logger.fdebug(module + 'multiple_dest_dirs:' + mylar.MULTIPLE_DEST_DIRS)
            logger.fdebug(module + 'dir: ' + rescan['ComicLocation'])
            logger.fdebug(module + 'os.path.basename: ' + os.path.basename(rescan['ComicLocation']))
            pathdir = os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(rescan['ComicLocation']))
            logger.info(module + ' Now checking files for ' + rescan['ComicName'] + ' (' + str(rescan['ComicYear']) + ') in :' + pathdir)
            tmpv = filechecker.listFiles(dir=pathdir, watchcomic=rescan['ComicName'], Publisher=rescan['ComicPublisher'], AlternateSearch=altnames)
            logger.fdebug(module + 'tmpv filecount: ' + str(tmpv['comiccount']))
            comiccnt += int(tmpv['comiccount'])
            fca.append(tmpv)
    else:
        fca.append(filechecker.listFiles(dir=archive, watchcomic=rescan['ComicName'], Publisher=rescan['ComicPublisher'], AlternateSearch=rescan['AlternateSearch']))
    fcb = []
    fc = {}
    #if len(fca) > 0:
    for ca in fca:
        i = 0
        while True:
            try:
                cla = ca['comiclist'][i]
            except (IndexError, KeyError) as e:
                break
            fcb.append({"ComicFilename":   cla['ComicFilename'],
                        "ComicLocation":   cla['ComicLocation'],
                        "ComicSize":       cla['ComicSize'],
                        "JusttheDigits":   cla['JusttheDigits'],
                        "AnnualComicID":   cla['AnnualComicID']})
            i+=1
    fc['comiclist'] = fcb
    is_cnt = myDB.select("SELECT COUNT(*) FROM issues WHERE ComicID=?", [ComicID])
    iscnt = is_cnt[0][0]
    #iscnt = rescan['Total']

    havefiles = 0
    if mylar.ANNUALS_ON:
        an_cnt = myDB.select("SELECT COUNT(*) FROM annuals WHERE ComicID=?", [ComicID])
        anncnt = an_cnt[0][0]
    else:
        anncnt = 0
    fccnt = comiccnt #int(fc['comiccount'])
    issnum = 1
    fcnew = []
    fn = 0
    issuedupechk = []
    annualdupechk = []
    issueexceptdupechk = []
    mc_issue = []
    mc_issuenumber = []
    reissues = myDB.select('SELECT * FROM issues WHERE ComicID=?', [ComicID])
    multiple_check = myDB.select('SELECT * FROM issues WHERE ComicID=? GROUP BY Int_IssueNumber HAVING (COUNT(Int_IssueNumber) > 1)', [ComicID])

    if len(multiple_check) == 0:
        logger.fdebug('No issues with identical issue numbering were detected for this series')
        mc_issuenumber = None
    else:
        logger.fdebug('Multiple issues with identical numbering were detected. Attempting to accomodate.')
        for mc in multiple_check:
            mc_issuenumber.append({"Int_IssueNumber": mc['Int_IssueNumber']})

    if not mc_issuenumber is None:
        for mciss in mc_issuenumber:
           mchk = myDB.select('SELECT * FROM issues WHERE ComicID=? AND Int_IssueNumber=?', [ComicID, mciss['Int_IssueNumber']])
           for mck in mchk:
              mc_issue.append({"Int_IssueNumber":   mck['Int_IssueNumber'],
                               "IssueYear":         mck['IssueDate'][:4],
                               "IssueID":           mck['IssueID']})


    logger.fdebug('mc_issue:' + str(mc_issue))

    issID_to_ignore = []
    issID_to_ignore.append(str(ComicID))
    issID_to_write = []
    ANNComicID = None

    while (fn < fccnt):
        haveissue = "no"
        issuedupe = "no"
        annualdupe = "no"
        try:
            tmpfc = fc['comiclist'][fn]
        except IndexError:
            logger.fdebug(module + ' Unable to properly retrieve a file listing for the given series.')
            logger.fdebug(module + ' Probably because the filenames being scanned are not in a parseable format')
            if fn == 0:
                return
            else:
                break
        temploc= tmpfc['JusttheDigits'].replace('_', ' ')

        temploc = re.sub('[\#\']', '', temploc)
        logger.fdebug(module + ' temploc: ' + str(temploc))
        if 'annual' not in temploc.lower():
            #remove the extension here
            extensions = ('.cbr', '.cbz', '.cb7')
            if temploc.lower().endswith(extensions):
                logger.fdebug(module + ' Removed extension for issue: ' + str(temploc))
                temploc = temploc[:-4]
            fcnew_af = re.findall('[^\()]+', temploc)
            fcnew = shlex.split(fcnew_af[0])

            fcn = len(fcnew)
            n = 0
            while True:
                try:
                    reiss = reissues[n]
                except IndexError:
                    break
                int_iss = helpers.issuedigits(reiss['Issue_Number'])
                issyear = reiss['IssueDate'][:4]
                old_status = reiss['Status']
                issname = reiss['IssueName']

                fnd_iss_except = 'None'

                fcdigit = helpers.issuedigits(temploc)

                if int(fcdigit) == int_iss:
                    logger.fdebug(module + ' [' + str(reiss['IssueID']) + '] Issue match - fcdigit: ' + str(fcdigit) + ' ... int_iss: ' + str(int_iss))

                    if '-' in temploc and temploc.find(reiss['Issue_Number']) > temploc.find('-'):
                        logger.fdebug(module + ' I have detected a possible Title in the filename')
                        logger.fdebug(module + ' the issue # has occured after the -, so I assume that it is part of the Title')
                        break

                    #baseline these to default to normal scanning
                    multiplechk = False
                    issuedupe = "no"
                    foundchk = False

                    #check here if muliple identical numbering issues exist for the series
                    if len(mc_issue) > 1:
                        for mi in mc_issue:
                            if mi['Int_IssueNumber'] == int_iss:
                                if mi['IssueID'] == reiss['IssueID']:
                                    logger.fdebug(module + ' IssueID matches to multiple issues : ' + str(mi['IssueID']) + '. Checking dupe.')
                                    logger.fdebug(module + ' miISSUEYEAR: ' + str(mi['IssueYear']) + ' -- issyear : ' + str(issyear))
                                    if any(mi['IssueID'] == d['issueid'] for d in issuedupechk):
                                        logger.fdebug(module + ' IssueID already within dupe. Checking next if available.')
                                        multiplechk = True
                                        break
                                    if (mi['IssueYear'] in tmpfc['ComicFilename']) and (issyear == mi['IssueYear']):
                                        logger.fdebug(module + ' Matched to year within filename : ' + str(issyear))
                                        multiplechk = False
                                        break
                                    else:
                                        logger.fdebug(module + ' Did not match to year within filename : ' + str(issyear))
                                        multiplechk = True
                    if multiplechk == True:
                        n+=1
                        continue

                    #this will detect duplicate filenames within the same directory.
                    for di in issuedupechk:
                        if di['fcdigit'] == fcdigit:
                            #base off of config - base duplication keep on filesize or file-type (or both)
                            logger.fdebug('[DUPECHECK] Duplicate issue detected [' + di['filename'] + '] [' + tmpfc['ComicFilename'] + ']')
                            # mylar.DUPECONSTRAINT = 'filesize' / 'filetype-cbr' / 'filetype-cbz'
                            logger.fdebug('[DUPECHECK] Based on duplication preferences I will retain based on : ' + mylar.DUPECONSTRAINT)
                            removedupe = False
                            if 'cbr' in mylar.DUPECONSTRAINT or 'cbz' in mylar.DUPECONSTRAINT:
                                if 'cbr' in mylar.DUPECONSTRAINT:
                                    #this has to be configured in config - either retain cbr or cbz.
                                    if tmpfc['ComicFilename'].endswith('.cbz'):
                                        #keep di['filename']
                                        logger.fdebug('[DUPECHECK-CBR PRIORITY] [#' + reiss['Issue_Number'] + '] Retaining currently scanned in file : ' + di['filename'])
                                        issuedupe = "yes"
                                        break
                                    else:
                                        #keep tmpfc['ComicFilename']
                                        logger.fdebug('[DUPECHECK-CBR PRIORITY] [#' + reiss['Issue_Number'] + '] Retaining newly scanned in file : ' + tmpfc['ComicFilename'])
                                        removedupe = True
                                elif 'cbz' in mylar.DUPECONSTRAINT:
                                    if tmpfc['ComicFilename'].endswith('.cbr'):
                                        #keep di['filename']
                                        logger.fdebug('[DUPECHECK-CBZ PRIORITY] [#' + reiss['Issue_Number'] + '] Retaining currently scanned in filename : ' + di['filename'])
                                        issuedupe = "yes"
                                        break
                                    else:
                                        #keep tmpfc['ComicFilename']
                                        logger.fdebug('[DUPECHECK-CBZ PRIORITY] [#' + reiss['Issue_Number'] + '] Retaining newly scanned in filename : ' + tmpfc['ComicFilename'])
                                        removedupe = True

                            if mylar.DUPECONSTRAINT == 'filesize':
                                if tmpfc['ComicSize'] <= di['filesize']:
                                    logger.fdebug('[DUPECHECK-FILESIZE PRIORITY] [#' + reiss['Issue_Number'] + '] Retaining currently scanned in filename : ' + di['filename'])
                                    issuedupe = "yes"
                                    break
                                else:
                                    logger.fdebug('[DUPECHECK-FILESIZE PRIORITY] [#' + reiss['Issue_Number'] + '] Retaining newly scanned in filename : ' + tmpfc['ComicFilename'])
                                    removedupe = True

                            if removedupe:
                                #need to remove the entry from issuedupechk so can add new one.
                                #tuple(y for y in x if y) for x in a
                                issuedupe_temp = []
                                tmphavefiles = 0
                                for x in issuedupechk:
                                    #logger.fdebug('Comparing x: ' + x['filename'] + ' to di:' + di['filename'])
                                    if x['filename'] != di['filename']:
                                        #logger.fdebug('Matched.')
                                        issuedupe_temp.append(x)
                                        tmphavefiles+=1
                                issuedupechk = issuedupe_temp
                                havefiles = tmphavefiles
                                logger.fdebug(issuedupechk)
                                foundchk = False
                                break

                    if issuedupe == "no":

                        if foundchk == False:
                            logger.fdebug(module + ' Matched...issue: ' + rescan['ComicName'] + '#' + reiss['Issue_Number'] + ' --- ' + str(int_iss))
                            havefiles+=1
                            haveissue = "yes"
                            isslocation = tmpfc['ComicFilename']
                            issSize = str(tmpfc['ComicSize'])
                            logger.fdebug(module + ' .......filename: ' + isslocation)
                            logger.fdebug(module + ' .......filesize: ' + str(tmpfc['ComicSize'])) 
                            # to avoid duplicate issues which screws up the count...let's store the filename issues then 
                            # compare earlier...
                            issuedupechk.append({'fcdigit':   fcdigit,
                                                 'filename':  tmpfc['ComicFilename'],
                                                 'filesize':  tmpfc['ComicSize'],
                                                 'issueyear': issyear,
                                                 'issueid':   reiss['IssueID']})
                            break

                if issuedupe == "yes":
                    logger.fdebug(module + ' I should break out here because of a dupe.')
                    break

                if haveissue == "yes" or issuedupe == "yes": break
                n+=1
        else:
            if tmpfc['AnnualComicID']:
                ANNComicID = tmpfc['AnnualComicID']
                logger.fdebug(module + ' Forcing ComicID to ' + str(ANNComicID) + ' in case of duplicate numbering across volumes.')
                reannuals = myDB.select('SELECT * FROM annuals WHERE ComicID=? AND ReleaseComicID=?', [ComicID, ANNComicID])
            else:
                reannuals = myDB.select('SELECT * FROM annuals WHERE ComicID=?', [ComicID])
                ANNComicID = ComicID
            # annual inclusion here.
            #logger.fdebug("checking " + str(temploc))
            fcnew = shlex.split(str(temploc))
            fcn = len(fcnew)
            n = 0
            reann = None
            while True:
                try:
                    reann = reannuals[n]
                except IndexError:
                    break
                int_iss = helpers.issuedigits(reann['Issue_Number'])
                logger.fdebug(module + ' int_iss:' + str(int_iss))

                issyear = reann['IssueDate'][:4]
                old_status = reann['Status']

                fcdigit = helpers.issuedigits(re.sub('annual', '', temploc.lower()).strip())
                logger.fdebug(module + ' fcdigit:' + str(fcdigit))

                if int(fcdigit) == int_iss:
                    logger.fdebug(module + ' [' + str(ANNComicID) + '] Annual match - issue : ' + str(int_iss))

                    #baseline these to default to normal scanning
                    multiplechk = False
                    annualdupe = "no"
                    foundchk = False

                    #check here if muliple identical numbering issues exist for the series
                    if len(mc_issue) > 1:
                        for mi in mc_issue:
                            if mi['Int_IssueNumber'] == int_iss:
                                if mi['IssueID'] == reann['IssueID']:
                                    logger.fdebug(module + ' IssueID matches to multiple issues : ' + str(mi['IssueID']) + '. Checking dupe.')
                                    logger.fdebug(module + ' miISSUEYEAR: ' + str(mi['IssueYear']) + ' -- issyear : ' + str(issyear))
                                    if any(mi['IssueID'] == d['issueid'] for d in issuedupechk):
                                        logger.fdebug(module + ' IssueID already within dupe. Checking next if available.')
                                        multiplechk = True
                                        break
                                    if (mi['IssueYear'] in tmpfc['ComicFilename']) and (issyear == mi['IssueYear']):
                                        logger.fdebug(module + ' Matched to year within filename : ' + str(issyear))
                                        multiplechk = False
                                        break
                                    else:
                                        logger.fdebug(module + ' Did not match to year within filename : ' + str(issyear))
                                        multiplechk = True
                    if multiplechk == True:
                        n+=1
                        continue

                    #this will detect duplicate filenames within the same directory.
                    for di in annualdupechk:
                        if di['fcdigit'] == fcdigit and di['issueid'] == reann['IssueID']:
                            #base off of config - base duplication keep on filesize or file-type (or both)
                            logger.fdebug('[DUPECHECK] Duplicate issue detected [' + di['filename'] + '] [' + tmpfc['ComicFilename'] + ']')
                            # mylar.DUPECONSTRAINT = 'filesize' / 'filetype-cbr' / 'filetype-cbz'
                            logger.fdebug('[DUPECHECK] Based on duplication preferences I will retain based on : ' + mylar.DUPECONSTRAINT)
                            removedupe = False
                            if 'cbr' in mylar.DUPECONSTRAINT or 'cbz' in mylar.DUPECONSTRAINT:
                                if 'cbr' in mylar.DUPECONSTRAINT:
                                    #this has to be configured in config - either retain cbr or cbz.
                                    if tmpfc['ComicFilename'].endswith('.cbz'):
                                        #keep di['filename']
                                        logger.fdebug('[DUPECHECK-CBR PRIORITY] [#' + reann['Issue_Number'] + '] Retaining currently scanned in file : ' + di['filename'])
                                        annualdupe = "yes"
                                        break
                                    else:
                                        #keep tmpfc['ComicFilename']
                                        logger.fdebug('[DUPECHECK-CBR PRIORITY] [#' + reann['Issue_Number'] + '] Retaining newly scanned in file : ' + tmpfc['ComicFilename'])
                                        removedupe = True
                                elif 'cbz' in mylar.DUPECONSTRAINT:
                                    if tmpfc['ComicFilename'].endswith('.cbr'):
                                        #keep di['filename']
                                        logger.fdebug('[DUPECHECK-CBZ PRIORITY] [#' + reann['Issue_Number'] + '] Retaining currently scanned in filename : ' + di['filename'])
                                        annualdupe = "yes"
                                        break
                                    else:
                                        #keep tmpfc['ComicFilename']
                                        logger.fdebug('[DUPECHECK-CBZ PRIORITY] [#' + reann['Issue_Number'] + '] Retaining newly scanned in filename : ' + tmpfc['ComicFilename'])
                                        removedupe = True

                            if mylar.DUPECONSTRAINT == 'filesize':
                                if tmpfc['ComicSize'] <= di['filesize']:
                                    logger.fdebug('[DUPECHECK-FILESIZE PRIORITY] [#' + reann['Issue_Number'] + '] Retaining currently scanned in filename : ' + di['filename'])
                                    annualdupe = "yes"
                                    break
                                else:
                                    logger.fdebug('[DUPECHECK-FILESIZE PRIORITY] [#' + reann['Issue_Number'] + '] Retaining newly scanned in filename : ' + tmpfc['ComicFilename'])
                                    removedupe = True

                            if removedupe:
                                #need to remove the entry from issuedupechk so can add new one.
                                #tuple(y for y in x if y) for x in a
                                annualdupe_temp = []
                                tmphavefiles = 0
                                for x in annualdupechk:
                                    logger.fdebug('Comparing x: ' + x['filename'] + ' to di:' + di['filename'])
                                    if x['filename'] != di['filename']:
                                        logger.fdebug('Matched.')
                                        annualdupe_temp.append(x)
                                        tmphavefiles+=1
                                annualdupechk = annualdupe_temp
                                havefiles = tmphavefiles
                                logger.fdebug(annualdupechk)
                                foundchk = False
                                break


                    if annualdupe == "no":
                        if foundchk == False:
                            logger.fdebug(module + ' Matched...annual issue: ' + rescan['ComicName'] + '#' + str(reann['Issue_Number']) + ' --- ' + str(int_iss))
                            havefiles+=1
                            haveissue = "yes"
                            isslocation = str(tmpfc['ComicFilename'])
                            issSize = str(tmpfc['ComicSize'])
                            logger.fdebug(module + ' .......filename: ' + str(isslocation))
                            logger.fdebug(module + ' .......filesize: ' + str(tmpfc['ComicSize']))
                            # to avoid duplicate issues which screws up the count...let's store the filename issues then
                            # compare earlier...
                            annualdupechk.append({'fcdigit':    int(fcdigit),
                                                  'anncomicid': ANNComicID,
                                                  'filename':   tmpfc['ComicFilename'],
                                                  'filesize':   tmpfc['ComicSize'],
                                                  'issueyear':  issyear,
                                                  'issueid':    reann['IssueID']})
                        break

                if annualdupe == "yes":
                    logger.fdebug(module + ' I should break out here because of a dupe.')
                    break

                if haveissue == "yes" or annualdupe == "yes": break
                n+=1

        if issuedupe == "yes" or annualdupe == "yes": pass
        else:
            #we have the # of comics, now let's update the db.
            #even if we couldn't find the physical issue, check the status.
            #-- if annuals aren't enabled, this will bugger out.
            writeit = True
            try:
                if mylar.ANNUALS_ON:
                    if 'annual' in temploc.lower():
                        if reann is None:
                            logger.fdebug(module + ' Annual present in location, but series does not have any annuals attached to it - Ignoring')
                            writeit = False
                        else:
                            iss_id = reann['IssueID']
                    else:
                        iss_id = reiss['IssueID']
                else:
                    if 'annual' in temploc.lower():
                        logger.fdebug(module + ' Annual support not enabled, but annual issue present within directory. Ignoring annual.')
                        writeit = False
                    else:
                        iss_id = reiss['IssueID']
            except:
                logger.warn(module + ' An error occured trying to get the relevant issue data. This is probably due to the series not having proper issue data.')
                logger.warn(module + ' you should either Refresh the series, and/or submit an issue on github in regards to the series and the error.')
                return

            if writeit == True:
                logger.fdebug(module + ' issueID to write to db:' + str(iss_id))
                controlValueDict = {"IssueID": iss_id}

                #if Archived, increase the 'Have' count.
                #if archive:
                #    issStatus = "Archived"

                if haveissue == "yes":
                    issStatus = "Downloaded"
                    newValueDict = {"Location":           isslocation,
                                    "ComicSize":          issSize,
                                    "Status":             issStatus
                                    }

                    issID_to_ignore.append(str(iss_id))

                    if ANNComicID:
#                   if 'annual' in temploc.lower():
                        #issID_to_write.append({"tableName":        "annuals",
                        #                       "newValueDict":     newValueDict,
                        #                       "controlValueDict": controlValueDict})
                        myDB.upsert("annuals", newValueDict, controlValueDict)
                        ANNComicID = None
                    else:
                        #issID_to_write.append({"tableName":        "issues",
                        #                       "valueDict":     newValueDict,
                        #                       "keyDict": controlValueDict})
                        myDB.upsert("issues", newValueDict, controlValueDict)
        fn+=1

#    if len(issID_to_write) > 0:
#        for iss in issID_to_write:
#            logger.info('writing ' + str(iss))
#            writethis = myDB.upsert(iss['tableName'], iss['valueDict'], iss['keyDict'])

    logger.fdebug(module + ' IssueID to ignore: ' + str(issID_to_ignore))

    #here we need to change the status of the ones we DIDN'T FIND above since the loop only hits on FOUND issues.
    update_iss = []
    tmpsql = "SELECT * FROM issues WHERE ComicID=? AND IssueID not in ({seq})".format(seq=','.join(['?'] *(len(issID_to_ignore) -1)))
    chkthis = myDB.select(tmpsql, issID_to_ignore)
#    chkthis = None
    if chkthis is None:
        pass
    else:
        for chk in chkthis:
            old_status = chk['Status']
            #logger.fdebug('old_status:' + str(old_status))
            if old_status == "Skipped":
                if mylar.AUTOWANT_ALL:
                    issStatus = "Wanted"
                else:
                    issStatus = "Skipped"
            elif old_status == "Archived":
                issStatus = "Archived"
            elif old_status == "Downloaded":
                issStatus = "Archived"
            elif old_status == "Wanted":
                issStatus = "Wanted"
            elif old_status == "Ignored":
                issStatus = "Ignored"
            elif old_status == "Snatched":   #this is needed for torrents, or else it'll keep on queuing..
                issStatus = "Snatched"
            else:
                issStatus = "Skipped"

            #logger.fdebug("new status: " + str(issStatus))

            update_iss.append({"IssueID": chk['IssueID'],
                               "Status":  issStatus})

    if len(update_iss) > 0:
        i = 0
        #do it like this to avoid DB locks...
        for ui in update_iss:
            controlValueDict = {"IssueID": ui['IssueID']}
            newStatusValue = {"Status": ui['Status']}
            myDB.upsert("issues", newStatusValue, controlValueDict)
            i+=1
        logger.info(module + ' Updated the status of ' + str(i) + ' issues for ' + rescan['ComicName'] + ' (' + str(rescan['ComicYear']) + ') that were not found.')

    logger.info(module + ' Total files located: ' + str(havefiles))
    foundcount = havefiles
    arcfiles = 0
    arcanns = 0
    # if filechecker returns 0 files (it doesn't find any), but some issues have a status of 'Archived'
    # the loop below won't work...let's adjust :)
    arcissues = myDB.select("SELECT count(*) FROM issues WHERE ComicID=? and Status='Archived'", [ComicID])
    if int(arcissues[0][0]) > 0:
        arcfiles = arcissues[0][0]
    arcannuals = myDB.select("SELECT count(*) FROM annuals WHERE ComicID=? and Status='Archived'", [ComicID])
    if int(arcannuals[0][0]) > 0:
        arcanns = arcannuals[0][0]

    if arcfiles > 0 or arcanns > 0:
        arcfiles = arcfiles + arcanns
        havefiles = havefiles + arcfiles
        logger.fdebug(module + ' Adjusting have total to ' + str(havefiles) + ' because of this many archive files:' + str(arcfiles))

    ignorecount = 0
    if mylar.IGNORE_HAVETOTAL:   # if this is enabled, will increase Have total as if in Archived Status
        ignores = myDB.select("SELECT count(*) FROM issues WHERE ComicID=? AND Status='Ignored'", [ComicID])
        if int(ignores[0][0]) > 0:
            ignorecount = ignores[0][0]
            havefiles = havefiles + ignorecount
            logger.fdebug(module + ' Adjusting have total to ' + str(havefiles) + ' because of this many Ignored files:' + str(ignorecount))

    snatchedcount = 0
    if mylar.SNATCHED_HAVETOTAL:   # if this is enabled, will increase Have total as if in Archived Status
        snatches = myDB.select("SELECT count(*) FROM issues WHERE ComicID=? AND Status='Snatched'", [ComicID])
        if int(snatches[0][0]) > 0:
            snatchedcount = snatches[0][0]
            havefiles = havefiles + snatchedcount
            logger.fdebug(module + ' Adjusting have total to ' + str(havefiles) + ' because of this many Snatched files:' + str(snatchedcount))

    #now that we are finished...
    #adjust for issues that have been marked as Downloaded, but aren't found/don't exist.
    #do it here, because above loop only cycles though found comics using filechecker.
    downissues = myDB.select("SELECT * FROM issues WHERE ComicID=? and Status='Downloaded'", [ComicID])
    downissues += myDB.select("SELECT * FROM annuals WHERE ComicID=? and Status='Downloaded'", [ComicID])
    if downissues is None:
        pass
    else:
        archivedissues = 0 #set this to 0 so it tallies correctly.
        for down in downissues:
            #print "downlocation:" + str(down['Location'])
            #remove special characters from
            #temploc = rescan['ComicLocation'].replace('_', ' ')
            #temploc = re.sub('[\#\'\/\.]', '', temploc)
            #print ("comiclocation: " + str(rescan['ComicLocation']))
            #print ("downlocation: " + str(down['Location']))
            if down['Location'] is None:
                logger.fdebug(module + ' Location does not exist which means file was not downloaded successfully, or was moved.')
                controlValue = {"IssueID":  down['IssueID']}
                newValue = {"Status":    "Archived"}
                myDB.upsert("issues", newValue, controlValue)
                archivedissues+=1
                pass
            else:
                comicpath = os.path.join(rescan['ComicLocation'], down['Location'])
                if os.path.exists(comicpath):
                    continue
                    #print "Issue exists - no need to change status."
                else:
                    if mylar.MULTIPLE_DEST_DIRS is not None and mylar.MULTIPLE_DEST_DIRS != 'None':
                        if os.path.exists(os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(rescan['ComicLocation']))):
                            #logger.fdebug('Issue(s) currently exist and found within multiple destination directory location')
                            continue
                    #print "Changing status from Downloaded to Archived - cannot locate file"
                    controlValue = {"IssueID":   down['IssueID']}
                    newValue = {"Status":    "Archived"}
                    myDB.upsert("issues", newValue, controlValue)
                    archivedissues+=1
        totalarc = arcfiles + archivedissues
        havefiles = havefiles + archivedissues  #arcfiles already tallied in havefiles in above segment
        logger.fdebug(module + ' arcfiles : ' + str(arcfiles))
        logger.fdebug(module + ' havefiles: ' + str(havefiles))
        logger.fdebug(module + ' I have changed the status of ' + str(archivedissues) + ' issues to a status of Archived, as I now cannot locate them in the series directory.')

    #combined total for dispay total purposes only.
    combined_total = iscnt + anncnt #(rescan['Total'] + anncnt)

    #let's update the total count of comics that was found.
    #store just the total of issues, since annuals gets tracked seperately.
    controlValueStat = {"ComicID":     rescan['ComicID']}
    newValueStat = {"Have":            havefiles,
                    "Total":           iscnt}

    myDB.upsert("comics", newValueStat, controlValueStat)
    logger.info(module + ' I have physically found ' + str(foundcount) + ' issues, ignored ' + str(ignorecount) + ' issues, snatched ' + str(snatchedcount) + ' issues, and accounted for ' + str(totalarc) + ' in an Archived state [ Total Issue Count: ' + str(havefiles) + ' / ' + str(combined_total) + ' ]')

    return
