import random
from DateTime import DateTime

from zope.component import adapts
from Products.CMFPlone import utils
from zope.interface import implements
from Products.Five import BrowserView
from persistent.dict import PersistentDict
from zope.component import queryMultiAdapter
from zope.cachedescriptors.property import Lazy
from eea.versions.interfaces import IGetVersions
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone import PloneMessageFactory as _
from zope.app.annotation.interfaces import IAnnotations
from zope.component.exceptions import ComponentLookupError
from eea.versions.interfaces import IVersionControl, IVersionEnhanced
from zope.interface import alsoProvides, directlyProvides, directlyProvidedBy


VERSION_ID = 'versionId'

def _reindex(obj):
    """ Reindex document
    """
    ctool = getToolByName(obj, 'portal_catalog')
    ctool.reindexObject(obj)


def _get_random(size=0):
    chars = "ABCDEFGHIJKMNOPQRSTUVWXYZ023456789"
    res = ''
    for k in range(size):
        res += random.choice(chars)
    return res


class VersionControl(object):
    """ Version adapter

    TODO: creating an adapter instance of an object has the side-effect of making
    that object versioned. This is not very intuitive
    """
    implements(IVersionControl)
    adapts(IVersionEnhanced)

    def __init__(self, context):
        """ Initialize adapter. """
        self.context = context
        annotations = IAnnotations(context)

        #Version ID
        ver = annotations.get(VERSION_ID)
        if ver is None:
            verData = {VERSION_ID: ''}
            annotations[VERSION_ID] = PersistentDict(verData)

    def getVersionId(self):
        """ Get version id. """
        anno = IAnnotations(self.context)
        ver = anno.get(VERSION_ID)
        return ver[VERSION_ID]

    def setVersionId(self, value):
        """ Set version id. """
        anno = IAnnotations(self.context)
        ver = anno.get(VERSION_ID)
        ver[VERSION_ID] = value

    versionId = property(getVersionId, setVersionId)

    def getVersionNumber(self):
        """ Return version number """
        #TODO: to be implemented
        pass


class GetVersions(object):
    """ Get all versions
    """
    implements(IGetVersions)

    def __init__(self, context, request):
        self.context = context
        self.request = request

    @Lazy
    def versions(self):
        ver = IVersionControl(self.context)
        verId = ver.getVersionId()

        if not verId:
            return {}

        cat = getToolByName(self.context, 'portal_catalog')
        query = {'getVersionId' : verId}
        if self.context.portal_membership.isAnonymousUser():
            query['review_state'] = 'published'

        brains = cat(**query)
        objects = [b.getObject() for b in brains]

        # Some objects don't have EffectiveDate so we have to sort them using CreationDate
        sortedObjects = sorted(objects, key=lambda o: o.effective_date or o.creation_date)

        versions = {}
        for index, ob in enumerate(sortedObjects):
            versions[index+1] = ob
        return versions

    def extract(self, version):
        """ Extract needed properties
        """
        wftool = getToolByName(version, 'portal_workflow')
        review_state = wftool.getInfoFor(version, 'review_state', '(Unknown)')

        # Get title of the workflow state
        GetWorkflowStateTitle = queryMultiAdapter((self.context, self.request), name=u'getWorkflowStateTitle')
        title_state = GetWorkflowStateTitle(object=version)

        field = version.getField('lastUpload') #TODO: this is a specific to dataservice
        if not field:
            value = version.getEffectiveDate()
            if not value:
                value = version.creation_date
        else:
            value = field.getAccessor(version)()

        if not isinstance(value, DateTime):
            value = None

        return {
            'title': version.title_or_id(),
            'url': version.absolute_url(),
            'date': value,
            'review_state': review_state,
            'title_state': title_state
        }

    def version_number(self):
        """ Return the current version number
        """
        for k,v in self.versions.items():
            if v == self.context:
                return k
        return 0

    def newest(self):
        """ Return info on new versions
        """
        versions = self.versions.items()
        versions.sort(reverse=True)

        res = []
        found = False
        uid = self.context.UID()
        for key, version in versions:
            if version.UID() == uid:
                found = True
                res.append(self.extract(version))
                break

        if not found:
            return []
        return res

    #TODO: add first_version method
    def latest_version(self):
        """Returns the latest version of an object"""

        if not self.versions:
            return self.context

        latest = sorted(self.versions.keys())[-1]
        return self.versions[latest]

    def oldest(self):
        """ Return old versions
        """
        versions = self.versions.items()
        versions.sort()

        res = []
        found = False
        uid = self.context.UID()
        for key, version in versions:
            self.extract(version)
            if version.UID() == uid:
                found = True
                break
            res.append(self.extract(version))

        if not found:
            return []

        res.reverse()
        return res

    def __call__(self):
        return self.versions


def get_versions_api(context):
    #TODO: at this moment the code sits in views, which makes it awkward to reuse
    #this API in python code and tests. There are the get_..._api() functions
    #Treat those views as API classes. This can and should be refactored
    return GetVersions(context, request=None)


def get_latest_version_link(context):
    ctrl = IVersionControl(context)
    anno = IAnnotations(context)
    ver = anno.get(VERSION_ID)
    return ver[VERSION_ID]


class GetLatestVersionLink(object):
    """ Get latest version link
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        return get_latest_version_link(self.context)


def get_version_id(context):
    res = None
    try:
        ver = IVersionControl(context)
        res = ver.getVersionId()
    except (ComponentLookupError, TypeError, ValueError):
        res = None

    return res


class GetVersionId(object):
    """ Get version ID
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        return get_version_id(self.context)

class GetWorkflowStateTitle(BrowserView):
    """ Returns the title of the workflow state of the given object
    """

    def __call__(self, object=None):
        title_state = 'Unknown'
        if object:
            wftool = getToolByName(self.context, 'portal_workflow')
            review_state = wftool.getInfoFor(object, 'review_state', '(Unknown)')

            try:
                title_state = wftool.getWorkflowsFor(object)[0].states[review_state].title
            except:
                pass

        return title_state


def get_version_id_api(context):
    return GetVersionId(context, request=None)


def has_versions(context):
    #TODO: this doesn't guarantee that there are versions
    #a better name for this would be "is_versioned"
    if IVersionEnhanced.providedBy(context):
        return True
    return False


class HasVersions(object):
    """ Check if object has versions
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        return has_versions(self.context)


class CreateVersion(object):
    """ This view, when called, will create a new version of an object
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        ver = create_version(self.context)
        return self.request.RESPONSE.redirect(ver.absolute_url())


def create_version(context, reindex=True):
    """Create a new version of an object"""

    pu = getToolByName(context, 'plone_utils')
    obj_id = context.getId()
    parent = utils.parent(context)

    # Adapt version parent (if case)
    if not IVersionEnhanced.providedBy(context):
        alsoProvides(context, IVersionEnhanced)
    verparent = IVersionControl(context)
    verId = verparent.getVersionId()
    if not verId:
        verId = _get_random(10)
        verparent.setVersionId(verId)
        _reindex(context)

    # Create version object
    clipb = parent.manage_copyObjects(ids=[obj_id])
    res = parent.manage_pasteObjects(clipb)
    new_id = res[0]['new_id']

    ver = getattr(parent, new_id)

    # Fixes the generated id: remove copy_of from ID
    #TODO: add -vX sufix to the ids
    id = ver.getId()
    new_id = id.replace('copy_of_', '')
    new_id = generateNewId(parent, new_id, ver.UID())
    parent.manage_renameObject(id=id, new_id=new_id)
    ver = parent[new_id]

    # Set effective date today
    ver.setCreationDate(DateTime())
    ver.setEffectiveDate(DateTime())

    if reindex:
        ver.reindexObject()
        _reindex(context)  #some indexed values of the context may depend on versions

    return ver


def assign_version(context, new_version):
    """Assign a specific version id to an object"""

    # Verify if there are more objects under this version
    cat = getToolByName(context, 'portal_catalog')
    brains = cat.searchResults({'getVersionId' : new_version,
                                'show_inactive': True})
    if brains and not IVersionEnhanced.providedBy(context):
        alsoProvides(context, IVersionEnhanced)
    if len(brains) == 1:
        target_ob = brains[0].getObject()
        if not IVersionEnhanced.providedBy(target_ob):
            alsoProvides(target_ob, IVersionEnhanced)

    # Set new version ID
    verparent = IVersionControl(context)
    verparent.setVersionId(new_version)
    context.reindexObject()


class AssignVersion(object):
    """ Assign new version ID
    """

    def __call__(self):
        pu = getToolByName(self.context, 'plone_utils')
        new_version = self.request.get('new-version', '')

        if new_version:
            assign_version(self.context, new_version)
            message = _(u'Version ID changed.')
        else:
            message = _(u'Please specify a valid Version ID.')

        pu.addPortalMessage(message, 'structure')
        return self.request.RESPONSE.redirect(self.context.absolute_url())


def revoke_version(context):
    """Revokes the context from being a version
    """
    obj = context
    verparent = IVersionControl(obj)
    verparent.setVersionId('')
    directlyProvides(obj, directlyProvidedBy(obj)-IVersionEnhanced)


class RevokeVersion(object):
    """ Revoke the context as being a version
    """

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def __call__(self):
        revoke_version(self.context)
        pu = getToolByName(self.context, 'plone_utils')
        message = _(u'Version revoked.')
        pu.addPortalMessage(message, 'structure')

        return self.request.RESPONSE.redirect(self.context.absolute_url())


def generateNewId(context, id, uid):
    tmp = id.split('-')[-1]
    try:
        num = int(tmp)
        id = '-'.join(id.split('-')[:-1])
    except ValueError:
        pass

    if id in context.objectIds():
        tmp_ob = getattr(context, id)
        if tmp_ob.UID() != uid:
            idx = 1
            while idx <= 100:
                new_id = "%s-%d" % (id, idx)
                new_ob = getattr(context, new_id, None)
                if new_ob:
                    if new_ob.UID() != uid:
                        idx += 1
                    else:
                        id = new_id
                        break
                else:
                    id = new_id
                    break
    return id


def versionIdHandler(obj, event):
    """ Set a versionId as annotation without setting the
        version marker interface just to have a perma link
        to last version
    """
    #hasVersions = obj.unrestrictedTraverse('@@hasVersions')
    if not has_versions(obj):
        verId = _get_random(10)
        anno = IAnnotations(obj)
        ver = anno.get(VERSION_ID)
        #TODO: tests fails with ver = None when adding an EEAFigure,
        #      remove "if ver:" after fix
        if ver:
            if not ver.values()[0]:
                ver[VERSION_ID] = verId
                _reindex(obj)
