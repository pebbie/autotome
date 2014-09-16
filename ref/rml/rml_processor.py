"""
rml_processor.py
Map RDF file from RML (http://semweb.mmlab.be/rml/spec.html) description

author: Peb Ruswono Aryan

dependencies: jsonpath_rw, lxml, requests
"""
from rdflib import Graph, plugin, Namespace, BNode, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL
#import requests
import csv
import json
import re
import time
import types
from lxml import etree
from jsonpath_rw import parse
import os
from urllib import quote_plus as quote
from functools import cmp_to_key

try:
    from io import StringIO
except:
    from cStringIO import StringIO

RML = Namespace('http://semweb.mmlab.be/ns/rml#')
RR = Namespace('http://www.w3.org/ns/r2rml#')
QL = Namespace('http://semweb.mmlab.be/ns/ql#')

matcher = {}
matcher[QL.XPath] = re.compile("\{[\w\.\d/@=-_\[\]]+\}")
matcher[QL.CSV] = re.compile("\{[\$\w\d\ \.-_]+\}")
matcher[QL.JSONPath] = re.compile("\{[\$\.\w\d/@=-_\[\]]+\}")

def iterate(obj, iterator, qlang):
    if qlang==QL.CSV:
        for o in obj:
            yield o
    elif qlang==QL.JSONPath:
        for o in parse(iterator).find(obj):
            yield o.value
    elif qlang==QL.XPath:
        for o in obj.xpath(iterator):
            yield o

def lookup(obj, ref, qlang):
    if qlang==QL.XPath:
        out = obj.xpath(ref)[0]
        if isinstance(out, etree._Element):
            return out.text
        else:
            return out
    elif qlang==QL.JSONPath:
        out = [o.value for o in parse(ref).find(obj)]
        return out
    elif qlang==QL.CSV:
        return obj.get(str(ref))

def process_template(obj, template, qlang, isuri=False):
    otemplate = template
    for pattern in matcher[qlang].findall(otemplate):
        rep = lookup(obj, pattern[1:-1], qlang)
        if isinstance(rep, list):
            rep = rep[0]
        if isuri:
            otemplate = otemplate.replace(pattern, quote(rep))
        else:
            otemplate = otemplate.replace(pattern, rep)
    return otemplate

if __name__ == "__main__":
    # RML Processor example
    fn = "rml\\example3\\example3.rml.ttl"
    #fn = "rml\\example4\\example4_Venue.rml.ttl"
    #fn = "rml\\example5\\museum-model.rml.ttl"
    #fn = "rml\\example6\\example.rml.ttl"
    #fn = "rml\\example7\\moon-walkers.rml.ttl"
    if len(sys.argv)>1:
        fn = sys.argv[1]
    
    if os.path.exists(fn):
        olddir = os.getcwd()
        fn = os.path.abspath(fn)
        os.chdir(os.path.dirname(fn))
    
    start = time.time()
    #
    # load mapping description (from local file) into RDF graph object
    #
    g = Graph().parse(fn, format="turtle")

    output = Graph()
    for k, v in g.namespace_manager.namespaces():
        if str(v) not in [RML, RR, QL]:
            output.bind(k, v)

    mapping_queue = []
    dependency = {}
    #
    # TriplesMap is equivalent of having rml:logicalSource
    #
    if (None, RML.logicalSource, None) in g:
        #
        # construct dependency ordering if there is a join condition among mapping
        #
        for parentMap in g.subjects(RML.logicalSource, None):
            mapping_queue.append(parentMap)
            if (None, RR.parentTriplesMap, parentMap) in g:
                # ?childMap rr:objectMap/rr:parentTriplesMap ?parentMap
                for dependant in g.subjects(RR.parentTriplesMap, parentMap):
                    childMap = g.value(object=g.value(predicate=RR.objectMap, object=dependant), predicate=RR.predicateObjectMap)
                    # rr:joinCondition/rr:parent ?parentRef
                    jc = [cond for cond in g.objects(dependant, RR.joinCondition)]
                    parentRef = [g.value(cond, RR.parent) for cond in jc]
                    
                    if len(parentRef)>1:
                        parentRef = tuple(parentRef)
                    else:
                        parentRef = parentRef[0]

                    if parentMap in dependency:
                        dependency[parentMap].append((parentRef, childMap))
                    else:
                        dependency[parentMap] = [(parentRef, childMap)]
                    
        def depth(node):
            if node in dependency:
                return 1+max([depth(child) for ref, child in dependency[node]])
            return 0

        if len(mapping_queue)>0:
            mapping_queue = [tmap for d, tmap in sorted([(depth(n), n) for n in mapping_queue], key=lambda x: x[0], reverse=True)]
        
        join_lookup = {}
        for mapping in mapping_queue:
            #
            # setup lookup structure beforehand
            #
            if mapping in dependency:
                join_lookup[mapping] = {}
                for ref, child in dependency[mapping]:
                    join_lookup[mapping][child] = {}
            #
            # read source description and how to do traversal in this source
            #
            print "--source desc.", repr(mapping)
            source = g.value(mapping, RML.logicalSource)

            ql = g.value(source, RML.queryLanguage)
            pm = matcher[ql]
            print ql
            if ql==QL.CSV:
                src = csv.DictReader(r)
            elif ql==QL.XPath:
                src = etree.parse(r)
            elif ql==QL.JSONPath:
                src = json.load(r)
            elif ql==RR.SQL2008:
                raise Exception("Language not yet supported")
                # source in ODBC connection string?
            else:
                raise Exception("Language not recognized")
            #
            # fetch source's content
            #
            # TODO: detect if it's local or http url
            #r = StringIO(requests.get(g.value(src, RML.sourceName)).text)
            r = file(g.value(source, RML.sourceName).toPython())

            iterator = g.value(source, RML.iterator)
            if iterator is not None:
                iterator = iterator.toPython()

            subj = BNode()
            smap = g.value(mapping, RR.subjectMap)
            cls = g.value(smap, RR["class"])
            if (smap, RR.template, None) in g:
                stemplate = g.value(smap, RR.template).toPython()
                tmp = matcher[ql].findall(stemplate)
                for iobj in iterate(src, iterator, ql):
                    subj = URIRef(process_template(iobj, stemplate, ql, True))

                    #
                    # store subj for join
                    #
                    #print repr(subj)
                    if mapping in dependency:
                        for ref, child in dependency[mapping]:
                            lval = lookup(iobj, ref, ql)
                            if isinstance(lval, list):
                                for l in lval:
                                    rval = quote(l)
                                    join_lookup[mapping][child][rval] = subj
                            else:
                                rval = quote(lval)
                                join_lookup[mapping][child][rval] = subj

                    if cls is not None:
                        output.add((subj, RDF.type, cls))
                    
                    for pomap in g.objects(mapping, RR.predicateObjectMap):
                        pred = g.value(pomap, RR.predicate)
                        omap = g.value(pomap, RR.objectMap)

                        #print "\t", pred,

                        obj = g.value(omap, RR.constant)
                        if obj is not None and (subj, pred, obj) not in output:
                            output.add((subj, pred, obj))

                        ttype = g.value(omap, RR.termType)
                        tlang = g.value(omap, RR.language)
                        dtype = g.value(omap, RR.datatype)

                        ovalue = None
                        if (omap, RML.reference, None) in g:
                            objref = g.value(omap, RML.reference)
                            ovalue = lookup(iobj, objref, ql)
                        elif (omap, RR.template, None) in g:
                            ovalue = process_template(iobj, g.value(omap, RR.template).toPython(), ql)
                        elif (omap, RR.parentTriplesMap, None) in g:
                            ttype = RR.IRI
                            parent = g.value(omap, RR.parentTriplesMap)
                            pref = g.value(g.value(omap, RR.joinCondition), RR.parent)

                            #ovalue = join_lookup[parent][mapping][pref]
                            cval = lookup(iobj, g.value(g.value(omap, RR.joinCondition), RR.child), ql)
                            if isinstance(cval, list):
                                ovalue = []
                                for item in cval:
                                    # item may not exists in parent
                                    qitem = quote(item)
                                    if qitem in join_lookup[parent][mapping]:
                                        ovalue.append(join_lookup[parent][mapping][qitem])
                            else:
                                ovalue = join_lookup[parent][mapping][quote(cval)]
                        
                        if ovalue is None: continue

                        if not isinstance(ovalue, list):
                            ovalue = [ovalue]

                        for objval in ovalue:
                            obj = None
                            if ttype is not None:
                                if ttype == RR.IRI:
                                    obj = URIRef(objval)
                                elif ttype == RR.Literal:
                                    if dtype is not None:
                                        if tlang is not None:
                                            obj = Literal(objval, datatype=dtype, language=tlang)
                                        else:
                                            obj = Literal(objval, datatype=dtype)
                                    else:
                                        obj = Literal(objval)
                            else:
                                if dtype is not None:
                                    if tlang is not None:
                                        obj = Literal(objval, datatype=dtype, language=tlang)
                                    else:
                                        obj = Literal(objval, datatype=dtype)
                                else:
                                    obj = Literal(objval)

                        
                            #print repr(obj)
                            if obj is not None and (subj, pred, obj) not in output:
                                output.add((subj, pred, obj))

        print "--output"
        output.serialize("output.n3", format="n3")
        #output.serialize("output.jsonld", format="json-ld")
        finish = time.time()
        print finish-start