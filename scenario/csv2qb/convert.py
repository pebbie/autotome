from rdflib import Graph, plugin, Namespace, BNode, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL
import requests
import csv
import re
import time
import types

try:
    from io import StringIO
except:
    from cStringIO import StringIO
#from rdflib.serializer import serializer
debug = False

ATTM = Namespace('http://pebbie.org/ont/autotome/')

def copy_tree(gsrc, gtgt, rootsubject, followpred=None):
    """copy tree in graph gsrc starting from root"""
    for p, o in gsrc.predicate_objects(rootsubject):
        gtgt.add((rootsubject, p, o))
        if followpred is None or p in followpred:
            copy_tree(gsrc, gtgt, o)

def prepare_template(s):
    """prepare_template update the S1:S2 pair into S1_S2"""
    return re.sub("\{(\w[\d\w_-]+):(\w[\d\w_-]+)\}", "{\g<1>_\g<2>}", s)

def getValue(graph, term, values={}, gparam=None):
    """getValue replace a blank node into an RDF Term or a set of RDF Term"""
    if type(term)==BNode:
        objtype = graph.value(term, RDF.type)
        if objtype == ATTM.ServiceInvoke:
            #
            # invoke external service
            #
            template = prepare_template(graph.value(term, ATTM.serviceTemplate).toPython())
            
            url = template.format(**values)
            #
            # specify service's HTTP method: default is plain GET
            #
            method = "GET"
            if (term, ATTM.serviceMethod, None) in graph:
                method = graph.value(term, ATTM.serviceTemplate).toPython().upper()
            if method == "GET":
                response = requests.get(url)
            #
            # handle service result: currently only handles URI in plain text as result
            #
            return URIRef(response.text)
        elif objtype == ATTM.ValueMap:
            #
            # use template as value: create a Literal
            #
            template = prepare_template(graph.value(term, ATTM.valueTemplate).toPython())

            lit_value = template.format(**values)
            if (term, ATTM.valueType, None) in graph:
                dtype = graph.value(term, ATTM.valueType)
                return Literal(lit_value, datatype=dtype)
            else:
                return Literal(lit_value)
        elif objtype == ATTM.OutputReflection:
            #
            # get value(s) from generated triples identified by attm:id
            #
            subj = graph.value(term, ATTM.idSelector)
            if subj is not None and unicode(subj) in values:
                subj = values[unicode(subj)]

            pred = graph.value(term, ATTM.predicateSelector)
            obj = graph.value(term, ATTM.objectSelector)
            
            return subj, pred, obj, gparam.triples((subj, pred, obj))
        else:
            #
            # other BNode: just clone all
            #
            if gparam is not None:
                copy_tree(graph, gparam, term)
                return term
    else:
        #
        # exception
        #
        print "NONE ", term, graph.value(term, RDF.type)
        return None

def do_map(graph, term, values={}, gparam=None):
    """the core mapping algorithm"""
    global debug
    subj = BNode()
    tmp = graph + gparam
    subtmp = None
    if (term, ATTM.objectId, None) in tmp:
        oid = graph.value(term, ATTM.objectId)
        if isinstance(oid, BNode):
            subtmp = getValue(tmp, oid, values, gparam)
            if subtmp is not None and not isinstance(subtmp, tuple):
                subj = URIRef(subtmp)
        elif isinstance(oid, URIRef):
            subj = oid

    _type = graph.value(term, RDF.type)
    if _type is not None:
        if _type == ATTM.Retraction:
            #
            # read the filter and execute inside the subject loop below
            #
            _ret_prop = graph.value(term, ATTM.onProperty)
            _retracted_values = []
            for val in graph.objects(term, ATTM.onValue):
                _retracted_values.append(val)
            #print _retracted_values

    if subtmp is not None and isinstance(subtmp, tuple):
        subjs = subtmp[3]
    else:
        subjs = [subj]

    for subj in subjs:
        if isinstance(subj, tuple):
            subj = subj[0]

        msg = graph.value(term, ATTM.message)
        if msg is not None: print msg

        if _type is not None and _type == ATTM.Retraction:
            #
            # Retraction only support for single onProperty but can be applied to multiple values
            #
            for _obj in gparam.objects(subj, _ret_prop):
                if len(_retracted_values)==0 or _obj in _retracted_values:
                    gparam.remove((subj, _ret_prop, _obj))

            continue

        for p, o in graph.predicate_objects(term):
            if p in [ATTM.objectSource, ATTM.objectId, ATTM.comment]: continue

            if p == ATTM.objectType:
                gparam.add((subj, RDF.type, o))
            elif isinstance(o, BNode):
                #
                # handle special case of OutputReflection: because the result might be a generator
                #
                if graph.value(o, RDF.type) == ATTM.OutputReflection:
                    v2 = getValue(graph, o, values, gparam)
                    if v2 is not None:
                        if isinstance(v2, tuple):
                            ss,pp,oo,gg = v2
                            #
                            # check for selection restriction
                            #
                            filter = None
                            if (o, ATTM.selectionRestriction, None) in graph:
                                filter = []
                                for selobj in graph.objects(o, ATTM.selectionRestriction):
                                    filter.append((graph.value(selobj, ATTM.onProperty), graph.value(selobj, ATTM.propertyValue)))

                            for _s, _p, _o in gg:
                                if ss is None:
                                    #
                                    # filter by property and value
                                    #
                                    skip = False
                                    if filter is not None:
                                        for fp, fo in filter:
                                            oo = gparam.value(_s, fp)
                                            #print fp, fo, oo
                                            if oo is not None and oo != fo:
                                                skip = True
                                                break
                                        if skip: continue
                                    gparam.add((subj, p, _s))
                                elif oo is None:
                                    gparam.add((subj, p, _o))
                                else:
                                    gparam.add((subj, p, _p))
                        else:
                            gparam.add((subj, p,  v2))
                else:
                    v1 = getValue(graph, o, values, gparam)
                    if v1 is not None:
                        gparam.add((subj, p, v1))
            elif isinstance(o, URIRef):
                gparam.add((subj, p, o))
            elif isinstance(o, Literal):
                gparam.add((subj, p, o))

def remap(prefix, mapping, delimiter="_"):
    """prepare dictionary to be used in the string format"""
    tmp = {}
    for k, v in mapping.items():
        tmp[prefix+delimiter+k] = v
    return tmp

if __name__ == "__main__":
    fn = "alokasi-anggaran-dan-pencairan-dana-pnpm.jsonld"

    start = time.time()
    #
    # load mapping description (from local file) into RDF graph object
    #
    with open(fn) as f:
        data = f.read()
    g = Graph().parse(data=data, format="json-ld")

    #
    # look for object of type attm:Mapping
    #
    if (None, RDF.type, ATTM.Mapping) in g:
        output = Graph()
        for mapping in g.subjects(RDF.type, ATTM.Mapping):
            #
            # read source description
            #
            print "--source desc.", repr(mapping)
            srcmap = {}
            for src in g.objects(mapping, ATTM.source):
                tmp = {}
                for p, o in g.predicate_objects(src):
                    if p == RDF.type: continue
                    tmp[p] = o

                #
                # fetch source's content from url (for now use a native handler)
                #
                # TODO: instead of downloading and run a native parser, invoke external service (HTTP POST) and 
                #       assume to receive a URL in the Location response header
                #       the URL is assumed to be a hydra API containing the interpreted content (from resource)
                r = requests.get(tmp[ATTM.resource])
                tmp["_:handler"] = csv.DictReader(StringIO(r.text))
                srcmap[src] = tmp["_:handler"]

            reflectMap = {}
            print "--global map"
            #
            # read global mapping and execute immediately
            #
            for src in g.objects(mapping, ATTM.globalMap):
                do_map(g, src, reflectMap, output)

            print "--content map", src
            #
            # read content mapping
            #
            for src in g.objects(mapping, ATTM.objectMap):
                objsrc = g.value(src, ATTM.objectSource)
                #
                # source traversal
                #
                for data in srcmap[objsrc]:
                    rdata = remap(objsrc, data)
                    do_map(g, src, rdata, output)

            print "--post processing"
            proc = g.value(mapping, ATTM.postProcess)
            while proc is not None and proc != RDF.nil:
                task = g.value(proc, RDF.first)
                do_map(g, task, reflectMap, output)
                proc = g.value(proc, RDF.rest)


        print "--output"
        output.serialize("output.n3", format="n3")
        output.serialize("output.jsonld", format="json-ld")
        finish = time.time()
        print finish-start