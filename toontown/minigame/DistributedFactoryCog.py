from panda3d.core import *
from direct.interval.IntervalGlobal import *
from direct.directnotify import DirectNotifyGlobal
from toontown.toonbase import ToontownGlobals, TTLocalizer
import FactoryGameGlobals
from toontown.suit import DistributedSuitBase
from direct.task.Task import Task
from toontown.suit import Suit
from direct.fsm import ClassicFSM, State
import random


class DistributedFactoryCog(DistributedSuitBase.DistributedSuitBase):
    notify = DirectNotifyGlobal.directNotify.newCategory('DistributedFactoryCog')

    def __init__(self, cr):
        try:
            self.DistributedFactoryCog_initialized
        except:
            self.DistributedFactoryCog_initialized = 1
            DistributedSuitBase.DistributedSuitBase.__init__(self, cr)
            self.fsm = ClassicFSM.ClassicFSM('DistributedFactoryCog', [State.State('Off', self.enterOff, self.exitOff, ['Stand']),
                                              State.State('Stand', self.enterStand, self.exitStand, ['Chase', 'Return']),
                                              State.State('Chase', self.enterChase, self.exitChase, ['Return', 'Stand']),
                                              State.State('Return', self.enterReturn, self.exitReturn, ['Stand', 'Chase'])], 'Off', 'Off')
            self.turnTrack = None
            self.chaseTrack = None
            self.returnTrack = None
            self.fsm.enterInitialState()
            self.chasing = 0
            self.state = None
            self.startChasePos = 0
            self.startChaseH = 0
            self.chaseTime = 0

    def generate(self):
        DistributedSuitBase.DistributedSuitBase.generate(self)

    def announceGenerate(self):
        DistributedSuitBase.DistributedSuitBase.announceGenerate(self)

    def initializeBodyCollisions(self, collIdStr):
        DistributedSuitBase.DistributedSuitBase.initializeBodyCollisions(self, collIdStr)
        self.sSphere = CollisionSphere(0, 0, 0, 2.85)
        name = self.uniqueName('toonSphere')
        self.sSphereNode = CollisionNode(name)
        self.sSphereNode.addSolid(self.sSphere)
        self.sSphereNodePath = self.attachNewNode(self.sSphereNode)
        self.sSphereNodePath.hide()
        self.sSphereBitMask = ToontownGlobals.WallBitmask
        self.sSphereNode.setCollideMask(self.sSphereBitMask)
        self.sSphere.setTangible(0)
        self.dSphere = CollisionSphere(0, 0, 0, 25)
        name = self.uniqueName('alertSphere')
        self.dSphereNode = CollisionNode(name)
        self.dSphereNode.addSolid(self.dSphere)
        self.dSphereNodePath = self.attachNewNode(self.dSphereNode)
        self.dSphereNodePath.hide()
        self.dSphereBitMask = ToontownGlobals.WallBitmask
        self.dSphereNode.setCollideMask(self.dSphereBitMask)
        self.dSphere.setTangible(0)
        self.cSphere = CollisionSphere(0, 0, 0, 90)
        name = self.uniqueName('visibleSphere')
        self.cSphereNode = CollisionNode(name)
        self.cSphereNode.addSolid(self.cSphere)
        self.cSphereNodePath = self.attachNewNode(self.cSphereNode)
        self.cSphereNodePath.hide()
        self.cSphereBitMask = ToontownGlobals.WallBitmask
        self.cSphereNode.setCollideMask(self.cSphereBitMask)
        self.cSphere.setTangible(0)


    def disable(self):
        self.notify.debug('DistributedSuit %d: disabling' % self.getDoId())
        self.setState('Off')
        if self.chaseTrack:
            del self.chaseTrack
            self.chaseTrack = None
        if self.returnTrack:
            del self.returnTrack
            self.returnTrack = None
        if self.turnTrack:
            self.turnTrack.finish()
            del self.turnTrack
            self.turnTrack = None
        taskMgr.remove(self.taskName('returnTask'))
        taskMgr.remove(self.taskName('checkStray'))
        taskMgr.remove(self.taskName('chaseTask'))
        taskMgr.remove(self.taskName('turnTask'))
        taskMgr.remove(self.taskName('checkVisible'))
        DistributedSuitBase.DistributedSuitBase.disable(self)
        return

    def delete(self):
        try:
            self.DistributedSuit_deleted
        except:
            self.DistributedSuit_deleted = 1
            self.notify.debug('DistributedSuit %d: deleting' % self.getDoId())
            del self.fsm
            if self.chaseTrack:
                self.chaseTrack.finish()
                del self.chaseTrack
                self.chaseTrack = None
            if self.returnTrack:
                self.returnTrack.finish()
                del self.returnTrack
                self.returnTrack = None
            if self.turnTrack:
                self.turnTrack.finish()
                del self.turnTrack
                self.turnTrack = None
            taskMgr.remove(self.taskName('returnTask'))
            taskMgr.remove(self.taskName('checkStray'))
            taskMgr.remove(self.taskName('chaseTask'))
            taskMgr.remove(self.taskName('turnTask'))
            taskMgr.remove(self.taskName('checkVisible'))
            DistributedSuitBase.DistributedSuitBase.delete(self)

    def enterStand(self):
        self.wantVisibleSphere(1)
        if self.generalDistanceCheck(120):
            self.__makeSelfInvisible()
        else:
            self.__makeSelfVisible(None)
        self.state = 'Stand'
        self.loop('neutral', 0)
        self.startChasePos = self.getPos()
        self.startChaseH = self.getH()
        self.lookForToon(1)
        self.wantHitToon(1)
        self.hideNametag2d()
        self.hideNametag3d()
        self.setPickable(False)
        if not self.turnTrack:
            delay = random.randint(1, 4)
            self.startTurnTask(delay)

    def exitStand(self):
        taskMgr.remove(self.taskName('turnTask'))
        if self.turnTrack:
            self.turnTrack.pause()
            del self.turnTrack
            self.turnTrack = None
        self.wantHitToon(0)

    def lookForToon(self, on = 1):
        if on:
            self.accept(self.uniqueName('enteralertSphere'), self.__handleToonAlert)
        else:
            self.ignore(self.uniqueName('enteralertSphere'))

    def wantHitToon(self, on = 1):
        if on:
            self.accept(self.uniqueName('entertoonSphere'), self.requestHit)
        else:
            self.ignore(self.uniqueName('entertoonSphere'))

    def wantVisibleSphere(self, on = 1):
        if on:
            self.accept(self.uniqueName('entervisibleSphere'), self.__makeSelfVisible)
        else:
            self.ignore(self.uniqueName('entervisibleSphere'))

    def __makeSelfVisible(self, collEntry):
        self.show()
        self.startCheckVisibleTask(1, 0)

    def __makeSelfInvisible(self):
        self.hide()
        taskMgr.remove(self.taskName('checkVisible'))

    def startCheckVisibleTask(self, on=1, delay=0):
        taskMgr.remove(self.taskName('checkVisible'))
        if on:
            loopVisibleTask = Task.loop(Task(self.checkVisibleTask), Task.pause(0.5))
            taskMgr.add(loopVisibleTask, self.taskName('checkVisible'))

    def checkVisibleTask(self, task):
        toonId = base.localAvatar.doId
        curPos = self.getPos()
        av = base.cr.doId2do.get(toonId, None)
        toonPos = av.getPos()
        distance = Vec3(curPos - toonPos).length()
        maxDistance = 120
        if distance > maxDistance:
            self.__makeSelfInvisible()
        return Task.done

    def generalDistanceCheck(self, maxDistance):
        curPos = self.getPos()
        av = base.cr.doId2do.get(base.localAvatar.doId, None)
        toonPos = av.getPos()
        distance = Vec3(curPos - toonPos).length()
        if distance > maxDistance:
            return True
        else:
            return False

    def __handleToonAlert(self, collEntry):
        self.notify.debug('%s: ahah!  i saw you' % self.doId)
        toonZ = base.localAvatar.getZ(render)
        suitZ = self.getZ(render)
        dZ = abs(toonZ - suitZ)
        if dZ < 8.0:
            self.sendUpdate('setAlert', [base.localAvatar.doId])

    def enterChase(self):
        self.state = 'Chase'
        self.setPlayRate(2, 'walk')
        self.startChaseTime = globalClock.getFrameTime()
        self.wantHitToon(1)
        self.startCheckStrayTask(1, 1)
        self.startChaseTask()

    def exitChase(self):
        taskMgr.remove(self.taskName('chaseTask'))
        if self.chaseTrack:
            self.chaseTrack.pause()
            del self.chaseTrack
            self.chaseTrack = None
        self.chasing = 0
        self.wantHitToon(0)
        self.setPlayRate(1, 'walk')
        self.startCheckStrayTask(0, 0)

    def enterReturn(self):
        self.state = 'Return'
        self.lookForToon(0)
        self.loop('neutral')
        self.wantHitToon(0)
        self.startReturnTask(1)

    def exitReturn(self):
        taskMgr.remove(self.taskName('checkStray'))
        taskMgr.remove(self.taskName('returnTask'))
        if self.returnTrack:
            self.returnTrack.pause()
            self.returnTrack = None
        return

    def startTurnTask(self, delay = 0):
        self.notify.debug('DistributedFactoryCog.startTurnTask delay=%s' % delay)
        taskMgr.remove(self.taskName('turnTask'))
        taskMgr.doMethodLater(delay, self.turnTask, self.taskName('turnTask'))

    def turnTask(self, task):
        if self.chaseTrack:
            self.chaseTrack.pause()
            del self.chaseTrack
            self.chaseTrack = None
        if self.returnTrack:
            self.returnTrack.pause()
            del self.returnTrack
            self.returnTrack = None
        if self.turnTrack:
            self.turnTrack.pause()
            del self.turnTrack
            self.turnTrack = None
        timeToTurn = 0.8
        mult = random.randint(1, 4)
        delay = random.randint(2, 7)
        operation = random.choice((1, -1))
        startHpr = self.getHpr()
        track = Sequence(Func(self.loop, 'walk', 0), LerpHprInterval(self, timeToTurn*mult, (startHpr[0] + 45*mult*operation, 0, 0), startHpr), Func(self.loop, 'neutral', 0), Func(self.startTurnTask, delay))
        self.turnTrack = track
        self.turnTrack.start()
        return

    def setConfrontToon(self, avId):
        self.notify.debug('DistributedFactoryCog.setConfrontToon %d' % avId)
        self.chasing = avId
        self.setState('Chase')

    def startChaseTask(self, delay = 0):
        self.notify.debug('DistributedFactoryCog.startChaseTask delay=%s' % delay)
        taskMgr.remove(self.taskName('chaseTask'))
        taskMgr.doMethodLater(delay, self.chaseTask, self.taskName('chaseTask'))

    def chaseTask(self, task):
        if not self.chasing:
            return Task.done
        av = base.cr.doId2do.get(self.chasing, None)
        if not av:
            self.notify.warning("avatar %s isn't here to chase" % self.chasing)
            return Task.done
        if globalClock.getFrameTime() - self.startChaseTime > 15.0:
            self.setReturn()
            return Task.done
        toonPos = av.getPos(self.getParent())
        suitPos = self.getPos()
        distance = Vec3(suitPos - toonPos).length()
        if self.chaseTrack:
            self.chaseTrack.pause()
            del self.chaseTrack
            self.chaseTrack = None
        if self.returnTrack:
            self.returnTrack.pause()
            del self.returnTrack
            self.returnTrack = None
        if self.turnTrack:
            self.turnTrack.pause()
            del self.turnTrack
            self.turnTrack = None
        targetPos = Vec3(toonPos[0], toonPos[1], toonPos[2])
        track = Sequence(Func(self.headsUp, targetPos[0], targetPos[1], targetPos[2]), Func(self.loop, 'walk', 0))
        chaseSpeed = 12.0
        duration = distance / chaseSpeed
        track.extend([LerpPosInterval(self, duration=duration, pos=Point3(targetPos), startPos=Point3(suitPos))])
        self.chaseTrack = track
        self.chaseTrack.start()
        self.startChaseTask(1)
        return

    def startCheckStrayTask(self, on = 1, delay=0):
        taskMgr.remove(self.taskName('checkStray'))
        if on:
            loopStrayTask = Task.loop(Task(self.checkStrayTask), Task.pause(0.5))
            taskMgr.add(loopStrayTask, self.taskName('checkStray'))

    def checkStrayTask(self, task):
        curPos = self.getPos()
        distance = Vec3(curPos - self.startChasePos).length()
        maxDistance = 40.0
        if distance > maxDistance:
            self.sendUpdate('setStrayed', [])
        return Task.done

    def requestHit(self, avId):
        self.sendUpdate('requestHit')

    def setHit(self, avId):
        if avId == 0:
            return
        if avId == base.localAvatar.getDoId():
            self.handleHit(avId)

    def handleHit(self, avId):
        av = base.cr.doId2do.get(avId)
        if av != None:
            av.stunToon(knockdown=1)
            if self.state == 'Chase':
                self.setState('Return')

    def getParentNodePath(self):
        return render

    def setPosition(self, x, y, z):
        self.reparentTo(self.getParentNodePath())
        self.setPos(x, y, z)

    def setReturn(self):
        self.notify.debug('DistributedFactoryCog.setReturn')
        self.setState('Return')

    def startReturnTask(self, delay = 0):
        taskMgr.remove(self.taskName('returnTask'))
        taskMgr.doMethodLater(delay, self.returnTask, self.taskName('returnTask'))

    def returnTask(self, task):
        if self.returnTrack:
            self.returnTrack.pause()
            self.returnTrack = None
        if self.chaseTrack:
            self.chaseTrack.pause()
            self.chaseTrack = None
        if self.turnTrack:
            self.turnTrack.pause()
            self.turnTrack = None
        targetPos = self.startChasePos
        track = Sequence(Func(self.headsUp, targetPos[0], targetPos[1], targetPos[2]), Func(self.loop, 'walk', 0))
        curPos = self.getPos()
        distance = Vec3(curPos - targetPos).length()
        duration = distance / 9.0
        track.append(LerpPosInterval(self, duration=duration, pos=Point3(targetPos), startPos=Point3(curPos)))
        track.append(Func(self.returnDone))
        self.returnTrack = track
        self.returnTrack.start()
        return

    def returnDone(self):
        self.setH(self.startChaseH)
        self.setState('Stand')
        self.wantHitToon(1)

