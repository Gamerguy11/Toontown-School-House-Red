from panda3d.core import *
from direct.interval.IntervalGlobal import *
from direct.fsm import ClassicFSM, State
from direct.fsm import State
from direct.directnotify import DirectNotifyGlobal
import DistributedSuitBase
from direct.task.Task import Task
import random
from toontown.toonbase import ToontownGlobals
from otp.level import LevelConstants
from toontown.distributed.DelayDeletable import DelayDeletable
from toontown.suit.Suit import *

class DistributedFactorySuit(DistributedSuitBase.DistributedSuitBase, DelayDeletable):
    notify = DirectNotifyGlobal.directNotify.newCategory('DistributedFactorySuit')

    def __init__(self, cr):
        try:
            self.DistributedSuit_initialized
        except:
            self.DistributedSuit_initialized = 1
            DistributedSuitBase.DistributedSuitBase.__init__(self, cr)
            self.fsm = ClassicFSM.ClassicFSM('DistributedSuit', [State.State('Off', self.enterOff, self.exitOff, ['Walk', 'Battle']),
             State.State('Walk', self.enterWalk, self.exitWalk, ['WaitForBattle', 'Battle', 'Chase']),
             State.State('Chase', self.enterChase, self.exitChase, ['WaitForBattle', 'Battle', 'Return']),
             State.State('Return', self.enterReturn, self.exitReturn, ['WaitForBattle', 'Battle', 'Walk']),
             State.State('Battle', self.enterBattle, self.exitBattle, ['Walk', 'Chase', 'Return']),
             State.State('WaitForBattle', self.enterWaitForBattle, self.exitWaitForBattle, ['Battle'])], 'Off', 'Off')
            self.path = None
            self.walkTrack = None
            self.chaseTrack = None
            self.returnTrack = None
            self.fsm.enterInitialState()
            self.chasing = 0
            self.startChasePos = 0
            self.startChaseH = 0
            self.paused = 0
            self.pauseTime = 0
            self.velocity = 3
            self.factoryRequest = None

        return

    def generate(self):
        DistributedSuitBase.DistributedSuitBase.generate(self)

    def setLevelDoId(self, levelDoId):
        self.notify.debug('setLevelDoId(%s)' % levelDoId)
        self.levelDoId = levelDoId

    def setCogId(self, cogId):
        self.cogId = cogId

    def setReserve(self, reserve):
        self.reserve = reserve

    def denyBattle(self):
        self.notify.warning('denyBattle()')
        place = self.cr.playGame.getPlace()
        if place.fsm.getCurrentState().getName() == 'WaitForBattle':
            place.setState('walk')

    def doReparent(self):
        self.notify.debug('Suit requesting reparenting')
        if not hasattr(self, 'factory'):
            self.notify.warning('no factory, get Redmond to look at DistributedFactorySuit.announceGenerate()')
        self.factory.requestReparent(self, self.spec['parentEntId'])
        if self.pathEntId:
            self.factory.setEntityCreateCallback(self.pathEntId, self.setPath)
        else:
            self.setPath()

    def setCogSpec(self, spec):
        self.spec = spec
        self.setPos(spec['pos'])
        self.setH(spec['h'])
        self.originalPos = spec['pos']
        self.escapePos = spec['pos']
        self.pathEntId = spec['path']
        self.behavior = spec['behavior']
        self.skeleton = spec['skeleton']
        self.revives = spec.get('revives')
        self.immune = spec.get('immune')
        self.boss = spec['boss']
        if self.reserve:
            self.reparentTo(hidden)
        else:
            self.doReparent()

    def comeOutOfReserve(self):
        self.doReparent()

    def getCogSpec(self, cogId):
        if self.reserve:
            return self.factory.getReserveCogSpec(cogId)
        else:
            return self.factory.getCogSpec(cogId)

    def announceGenerate(self):
        self.notify.debug('announceGenerate %s' % self.doId)

        def onFactoryGenerate(factoryList, self = self):
            self.factory = factoryList[0]

            def onFactoryReady(self = self):
                self.notify.debug('factory ready, read spec')
                spec = self.getCogSpec(self.cogId)
                self.setCogSpec(spec)
                self.factoryRequest = None
                return

            self.factory.setEntityCreateCallback(LevelConstants.LevelMgrEntId, onFactoryReady)

        self.factoryRequest = self.cr.relatedObjectMgr.requestObjects([self.levelDoId], onFactoryGenerate)
        DistributedSuitBase.DistributedSuitBase.announceGenerate(self)

    def disable(self):
        self.ignoreAll()
        if self.factoryRequest is not None:
            self.cr.relatedObjectMgr.abortRequest(self.factoryRequest)
            self.factoryRequest = None
        self.notify.debug('DistributedSuit %d: disabling' % self.getDoId())
        self.setState('Off')
        if self.walkTrack:
            del self.walkTrack
            self.walkTrack = None
        if self.chaseTrack:
            del self.chaseTrack
            self.chaseTrack = None
        if self.returnTrack:
            del self.returnTrack
            self.returnTrack = None
        DistributedSuitBase.DistributedSuitBase.disable(self)
        taskMgr.remove(self.taskName('returnTask'))
        taskMgr.remove(self.taskName('checkStray'))
        taskMgr.remove(self.taskName('chaseTask'))
        return

    def delete(self):
        try:
            self.DistributedSuit_deleted
        except:
            self.DistributedSuit_deleted = 1
            self.notify.debug('DistributedSuit %d: deleting' % self.getDoId())
            del self.fsm
            DistributedSuitBase.DistributedSuitBase.delete(self)

    def d_requestBattle(self, pos, hpr):
        self.cr.playGame.getPlace().setState('WaitForBattle')
        self.factory.lockVisibility(zoneNum=self.factory.getEntityZoneEntId(self.spec['parentEntId']))
        self.sendUpdate('requestBattle', [pos[0],
         pos[1],
         pos[2],
         hpr[0],
         hpr[1],
         hpr[2]])

    def handleBattleBlockerCollision(self):
        self.__handleToonCollision(None)
        return

    def __handleToonCollision(self, collEntry):
        if collEntry:
            if collEntry.getFromNodePath().getParent().getKey() != localAvatar.getKey():
                return
        if hasattr(self, 'factory') and hasattr(self.factory, 'lastToonZone'):
            factoryZone = self.factory.lastToonZone
            unitsBelow = self.getPos(render)[2] - base.localAvatar.getPos(render)[2]
            if factoryZone == 24 and unitsBelow > 10.0:
                self.notify.warning('Ignoring toon collision in %d from %f below.' % (factoryZone, unitsBelow))
                return
        if not base.localAvatar.wantBattles:
            return
        toonId = base.localAvatar.getDoId()
        self.notify.debug('Distributed suit %d: requesting a Battle with toon: %d' % (self.doId, toonId))
        self.d_requestBattle(self.getPos(), self.getHpr())
        self.setState('WaitForBattle')
        return None

    def setPath(self):
        self.notify.debug('setPath %s' % self.doId)
        if self.pathEntId != None:
            parent = self.factory.entities.get(self.spec['parentEntId'])
            self.path = self.factory.entities.get(self.pathEntId)
            self.idealPathNode = self.path.attachNewNode('idealPath')
            self.reparentTo(self.idealPathNode)
            self.setPos(0, 0, 0)
            self.path.reparentTo(parent)
            self.walkTrack = self.path.makePathTrack(self.idealPathNode, self.velocity, self.uniqueName('suitWalk'))
        self.setState('Walk')
        return

    def initializeBodyCollisions(self, collIdStr):
        DistributedSuitBase.DistributedSuitBase.initializeBodyCollisions(self, collIdStr)
        self.sSphere = CollisionSphere(0, 0, 0, 15)
        name = self.uniqueName('toonSphere')
        self.sSphereNode = CollisionNode(name)
        self.sSphereNode.addSolid(self.sSphere)
        self.sSphereNodePath = self.attachNewNode(self.sSphereNode)
        self.sSphereNodePath.hide()
        self.sSphereBitMask = ToontownGlobals.WallBitmask
        self.sSphereNode.setCollideMask(self.sSphereBitMask)
        self.sSphere.setTangible(0)
        self.dSphere = CollisionSphere(0, 0, 0, 35)
        name = self.uniqueName('alertSphere')
        self.dSphereNode = CollisionNode(name)
        self.dSphereNode.addSolid(self.dSphere)
        self.dSphereNodePath = self.attachNewNode(self.dSphereNode)
        self.dSphereNodePath.hide()
        self.dSphereBitMask = ToontownGlobals.WallBitmask
        self.dSphereNode.setCollideMask(self.dSphereBitMask)
        self.dSphere.setTangible(0)

    def enableBattleDetect(self, name, handler):
        DistributedSuitBase.DistributedSuitBase.enableBattleDetect(self, name, handler)
        self.lookForToon(1)

    def disableBattleDetect(self):
        DistributedSuitBase.DistributedSuitBase.disableBattleDetect(self)
        self.lookForToon(0)

    def subclassManagesParent(self):
        return 1

    def enterWalk(self, ts = 0):
        self.enableBattleDetect('walk', self.__handleToonCollision)
        self.wideBattleCollision(1)
        if self.path:
            if self.walkTrack:
                self.walkTrack.loop()
                self.walkTrack.pause()
                if self.paused:
                    self.walkTrack.setT(self.pauseTime)
                else:
                    self.walkTrack.setT(ts)
                self.walkTrack.resume()
            self.loop('walk', 0)
            self.setPlayRate(1, 'walk')
            self.paused = 0
        else:
            self.loop('neutral', 0)

    def exitWalk(self):
        if self.walkTrack:
            self.pauseTime = self.walkTrack.pause()
            self.paused = 1

    def wideBattleCollision(self, on = 1):
        if on:
            self.accept(self.uniqueName('entertoonSphere'), self.__handleToonCollision)
        else:
            self.ignore(self.uniqueName('entertoonSphere'))

    def lookForToon(self, on = 1):
        if self.behavior in ['chase']:
            if on:
                self.accept(self.uniqueName('enteralertSphere'), self.__handleToonAlert)
            else:
                self.ignore(self.uniqueName('enteralertSphere'))

    def __handleToonAlert(self, collEntry):
        self.notify.debug('%s: ahah!  i saw you' % self.doId)
        toonZ = base.localAvatar.getZ(render)
        suitZ = self.getZ(render)
        dZ = abs(toonZ - suitZ)
        if dZ < 8.0:
            self.sendUpdate('setAlert', [base.localAvatar.doId])

    def resumePath(self, state):
        self.setState('Walk')

    def enterChase(self):
        self.setPlayRate(2, 'walk')
        self.startChaseH = self.getH()
        self.startChasePos = self.getPos()
        self.enableBattleDetect('walk', self.__handleToonCollision)
        self.wideBattleCollision(0)
        self.startChaseTime = globalClock.getFrameTime()
        self.startCheckStrayTask(1, 1)
        self.startChaseTask()

    def exitChase(self):
        taskMgr.remove(self.taskName('chaseTask'))
        if self.chaseTrack:
            self.chaseTrack.pause()
            del self.chaseTrack
            self.chaseTrack = None
        self.chasing = 0
        self.setPlayRate(1, 'walk')
        self.startCheckStrayTask(0, 0)
        return

    def setConfrontToon(self, avId):
        self.notify.debug('DistributedFactorySuit.setConfrontToon %d' % avId)
        self.chasing = avId
        self.setState('Chase')

    def startChaseTask(self, delay = 0):
        self.notify.debug('DistributedFactorySuit.startChaseTask delay=%s' % delay)
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
        targetPos = Vec3(toonPos[0], toonPos[1], suitPos[2])
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

    def enterReturn(self):
        self.setPlayRate(1, 'walk')
        self.enableBattleDetect('walk', self.__handleToonCollision)
        self.wideBattleCollision(0)
        self.lookForToon(0)
        self.loop('neutral')
        self.startReturnTask(1)

    def exitReturn(self):
        taskMgr.remove(self.taskName('checkStray'))
        taskMgr.remove(self.taskName('returnTask'))
        if self.returnTrack:
            self.returnTrack.pause()
            self.returnTrack = None
        return

    def setReturn(self):
        self.notify.debug('DistributedFactorySuit.setReturn')
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
        self.startChasePos = 0
        self.setH(self.startChaseH)
        self.startChaseH = 0
        self.setState('Walk')
        if not self.path:
            self.loop('neutral')

    def setActive(self, active):
        if active:
            self.setState('Walk')
        else:
            self.setState('Off')

    def disableBodyCollisions(self):
        self.disableBattleDetect()
        self.enableRaycast(0)
        if self.cRayNodePath:
            self.cRayNodePath.removeNode()
        if hasattr(self, 'cRayNode'):
            del self.cRayNode
        if hasattr(self, 'cRay'):
            del self.cRay
        if hasattr(self, 'lifter'):
            del self.lifter

    def removeCollisions(self):
        self.enableRaycast(0)
        self.cRay = None
        self.cRayNode = None
        self.cRayNodePath = None
        self.lifter = None
        self.cTrav = None
        return

    def setVirtual(self, isVirtual = 1):
        self.virtual = isVirtual
        if self.virtual:
            self.makeVirtual()

    def getVirtual(self):
        return self.virtual
