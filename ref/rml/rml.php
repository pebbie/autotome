<?php
/*
 * RML Processor controller logic for botol
 * dependency : 
 * + EasyRdf
 * + jsonpath
 * + [Spreadsheet-Reader](https://github.com/nuovo/spreadsheet-reader)

 * Notes :
 * for spreadsheet there is a small fix, see my comment in https://github.com/nuovo/spreadsheet-reader/issues/69
 */

function _exp($s)
{
    return EasyRdf_Namespace::expand($s);
}

function _depth($node, $dep)
{
    if(!array_key_exists($node, $dep)) return 0;
    $branch = array();
    foreach($dep[$node] as $key => $value){
        $branch[] = _depth($value[1], $dep);
    }
    //print_r($branch);
    return 1+max($branch);
}

function extract_vars($template)
{
    $out = array();
    $tmp = explode("{", $template);
    unset($tmp[0]);
    foreach($tmp as $key => $value)
    {
        $tmp[$key] = substr($value, 0, strpos($value,"}"));
    }
    return $tmp;
}

class RmlSource
{
    public function open($location)
    {
        throw new EasyRdf_Exception(
            "This method should be overridden by sub-classes."
        );
    }

    public function iterate($iterator, $ref=null)
    {
        throw new EasyRdf_Exception(
            "This method should be overridden by sub-classes."
        );
    }

    public function lookup($reference, $ref=null)
    {
        throw new EasyRdf_Exception(
            "This method should be overridden by sub-classes."
        );
    }
}

class JsonSource extends RmlSource
{
    private $parser;
    private $json;

    public function __construct()
    {
        if($this->parser==null)
            $this->parser = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
    }

    public function open($location)
    {
        $this->json = $this->parser->decode(file_get_contents($location));
    }

    public function iterate($iterator, $ref=null)
    {
        //echo $iterator;
        $tmp = jsonPath($this->json, $iterator);
        if($tmp===false)
            return array($this->json);
        if ($ref==null)
            return jsonPath($this->json, $iterator);
        else
            return jsonPath($ref, $iterator);
    }

    public function lookup($reference, $ref=null)
    {
        if ($ref==null || $ref===false)
            return jsonPath($this->json, $reference);
        else
            return jsonPath($ref, $reference);
    }
}

class CsvSource extends RmlSource
{
    private $csv;
    private $header;
    private $delimiter = ',';

    public function __construct()
    {
        
    }

    public function __destruct()
    {
        if($this->csv)
            fclose($this->csv);
    }

    public function open($location)
    {
        $this->csv = fopen($location, "r");
        $this->header = fgetcsv($this->csv, 1000, $this->delimiter);
        foreach($this->header as $idx => $head)
        {
            $this->header[$idx] = str_replace(" ", "_", $head);
        }
    }

    public function iterate($iterator, $ref=null)
    {
        $tmp = array();
        while(($row = fgetcsv($this->csv, 1000, $this->delimiter)) != FALSE)
        {
            #print_r($row);
            $tmp[] = array_combine($this->header, $row);
        }
        //$this->row = $row;
        //return array();
        return $tmp;
    }

    public function lookup($reference, $ref)
    {
        $rr = str_replace(" ", "_", $reference);
        #print_r($ref);
        #echo $rr, $ref[$rr], array_key_exists($rr, $ref), "\n";
        if(array_key_exists($rr, $ref))
            return $ref[$rr];
        else return null;
    }
}

class XmlSource extends RmlSource
{
    private $xml;

    public function __construct()
    {
        
    }

    public function open($location)
    {
        //echo $location, file_exists($location);
        $this->xml = simplexml_load_string(file_get_contents($location));
    }

    public function iterate($iterator, $ref=null)
    {
        return $this->xml->xpath($iterator);
    }

    public function lookup($reference, $ref=null)
    {
        if($ref)
            return $ref->xpath($reference);
        else
            return $this->xml->xpath($reference);
    }
}

class BibtexSource extends RmlSource
{
    private $bib;
    private $obj;
    private $json;

    public function __construct()
    {
        $this->bib = new Structures_BibTex();
        $this->json = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
    }

    public function open($location)
    {
        $this->bib->loadFile($location);
        $this->bib->parse();
    }

    public function iterate($iterator, $ref=null)
    {
        $tmp = jsonPath($this->json->decode($this->json->encode($this->bib->data)), $iterator);
        if($tmp==false)
            return $this->bib->data;
        else
            return $tmp;
    }

    public function lookup($reference, $ref=null)
    {
        if ($ref==null || $ref===false)
            return jsonPath($this->bib->data, $reference);
        else
            return jsonPath($ref, $reference);
        /*
        if(array_key_exists($reference, $ref))
            return $ref[$reference];
        else return null;
        */
    }
}

class SpreadsheetSource extends RmlSource
{
    private $reader;
    private $sheets;
    private $header;

    public function __construct()
    {
    }

    public function __destruct()
    {
    }

    public function open($location)
    {
        $this->reader = new SpreadsheetReader($location);
        $this->sheets = $this->reader->Sheets();
    }

    public function iterate($iterator, $ref=null)
    {
        if(strlen($iterator)>0)
            $this->reader->ChangeSheet(array_search($iterator, $this->sheets));
        
        $this->header = $this->reader->current();
        $this->reader->next();
        foreach($this->header as $idx => $head)
        {
            $this->header[$idx] = str_replace(" ", "_", $head);
        }

        $tmp = array();
        foreach($this->reader as $row)
        {
            #print_r($row);
            $tmp[] = array_combine($this->header, $row);
        }
        //$this->row = $row;
        //return array();
        return $tmp;
    }

    public function lookup($reference, $ref)
    {
        $rr = str_replace(" ", "_", $reference);
        #print_r($ref);
        #echo $rr, $ref[$rr], array_key_exists($rr, $ref), "\n";
        if(array_key_exists($rr, $ref))
            return $ref[$rr];
        else return null;
    }
}

route("/rml/:path", function($arg){
    //header("Content-type: text/json");
    //header("Content-type: text/turtle");
    header("Content-type: text/plain");
    $mapper = array('JSONPath'=>'JsonSource', 'CSV'=>'CSVSource', 'XPath'=>'XmlSource', 'Bibtex'=>'BibtexSource', 'Spreadsheet'=>'SpreadsheetSource');
    $src_path = "tmp/";
    $rml_file = $src_path.$arg["path"].".rml.ttl";
    #echo file_exists($rml_file);
    //echo $arg["path"], $rml_file;
    #print_r(EasyRdf_Format::getFormats());
    EasyRdf_Namespace::set("rml", "http://semweb.mmlab.be/ns/rml#");
    EasyRdf_Namespace::set("rr", "http://www.w3.org/ns/r2rml#");
    EasyRdf_Namespace::set("ql", "http://semweb.mmlab.be/ns/ql#");
    #print_r(EasyRdf_Namespace::namespaces());
    #echo EasyRdf_Namespace::expand("rml:logicalSource");
    $graph = new EasyRDF_Graph();
    $output = new EasyRDF_Graph();

    $graph->parse(file_get_contents($rml_file), "turtle");
    $dependency = array();
    $mapping = array();

    
    //echo $graph->serialise(EasyRdf_Format::getFormat("n3"));

    foreach($graph->resourcesMatching(_exp("rml:logicalSource")) as $key => $TripleMap)
    {
        $mapping[] = $TripleMap;
        foreach($graph->resourcesMatching(_exp("rr:parentTriplesMap"), $TripleMap) as $key => $JoinMap)
        {
            if($JoinMap != NULL)
            {
                $objmap = $graph->resourcesMatching(_exp("rr:objectMap"), $JoinMap);
                //print_r($objmap[0]);
                //break;
                $ChildMap = $graph->resourcesMatching(_exp("rr:predicateObjectMap"), $objmap[0]);
                //$ChildMap = $graph->resourcesMatching(_exp("rr:predicateObjectMap"), $graph->resourcesMatching(_exp("rr:objectMap"), $JoinMap)[0]);

                $jc = $JoinMap->all("rr:joinCondition");

                $parentRef = array();
                foreach($jc as $key => $joincond)
                {
                    $parentRef[] = $joincond->get("rr:parent")->getValue();
                }
                
                if(!array_key_exists($TripleMap->getUri(), $dependency))
                {
                    $dependency[$TripleMap->getUri()] = array();
                }
                $dependency[$TripleMap->getUri()][] = array($parentRef, $ChildMap[0]->getUri());
            }
        }
    }
    
    $adepth = array();
    foreach($mapping as $k => $map)
    {
        $adepth[$map->getUri()] =_depth($map->getUri(), $dependency);
    }
    arsort($adepth);

    $lookup = array();
    foreach($adepth as $mapuri => $depth)
    {
        #echo $mapuri, "\n";
        if(array_key_exists($mapuri, $dependency))
        {
            $lookup[$mapuri] = array();
            foreach($dependency[$mapuri] as $kd => $depmap)
            {
                $lookup[$mapuri][$depmap[1]] = array();
            }
        }

        $map = $graph->resource($mapuri);
        $ls = $map->get("rml:logicalSource");
        $sourceName = $ls->get("rml:sourceName");
        $ql = $ls->get("rml:queryLanguage");
        $iterator = $ls->get("rml:iterator");
        //echo $sourceName, " ", $iterator," ", $ql->localName(), "\n";
        $format_reader = new $mapper[$ql->localName()]();
        if(substr( $sourceName, 0, 4 ) === "http")
            $format_reader->open($sourceName);
        else
            $format_reader->open($src_path.$sourceName);

        $_subj = $map->get("rr:subject");
        $_pred = $map->all("rr:predicate");

        $smap = $map->get("rr:subjectMap");
        $pomap = $map->all("rr:predicateObjectMap");

        if($_subj)
        {
            $collection = array($_subj);
            $template = null;
            $class = null;
            $sconst = null;
        }
        else
        {
            $sconst = $smap->get("rr:constant");
            $class = $smap->get("rr:class");
            $template = $smap->get("rr:template");
            
            $vars = extract_vars($template);
            $collection = $format_reader->iterate($iterator);
        }
        foreach($collection as $k => $obj)
        {
            #print_r($obj);
            if($template){
                $url = $template;
                foreach($vars as $k => $var){
                    $val = $format_reader->lookup($var, $obj);
                    if(is_array($val))
                        $val = $val[0];
                    $url = str_replace("{".$var."}", urlencode($val), $url);
                }
                $subj = $output->resource($url);
            }
            
            if($sconst)
            {
                $subj = $sconst;
                $url = $subj->getUri();
            }
            
            if($class){
                $output->add($subj, "rdf:type", $class);
            }

            if(array_key_exists($mapuri, $dependency))
            {
                foreach($dependency[$mapuri] as $kd => $depmap)
                {
                    $tmp = array();
                    $mapping = array();
                    $multi = false;
                    $keys = array();
                    foreach($depmap[0] as $kk => $depkey)
                    {
                        $keys[] = $depkey;
                        $val = $format_reader->lookup($depkey, $obj);
                        if(is_array($val))
                            if(count($val)==1)
                                $val = "".$val[0];
                            else
                                $multi = true;
                        
                        //if(is_array($val))
                        //    $val = $val[0];
                        //$mapping[$depkey] = "".$val;
                        $mapping[$depkey] = $val;
                    }
                    if($multi){
                        //print_r($mapping);
                        $firstkey = $keys[0];
                        //echo $firstkey, "\n";
                        foreach($mapping[$firstkey] as $ik => $iv)
                        {
                            $tmap = array();
                            foreach($depmap[0] as $kk => $depkey)
                            {
                                $tmap[$depkey] = $mapping[$depkey][$ik];
                            }
                            $tmp = array();
                            $tmp[] = $tmap;
                            $tmp[] = $url;
                            //print_r($tmp);
                            $lookup[$mapuri][$depmap[1]][] = $tmp;
                        }
                    }
                    else{
                        $tmp[] = $mapping;
                        $tmp[] = $url;
                        $lookup[$mapuri][$depmap[1]][] = $tmp;
                    }
                }
            }

            foreach($pomap as $kp => $kv)
            {
                $value = "";
                $pred = $kv->get("rr:predicate");
                $_obj = $kv->get("rr:object");
                //echo $pred->getUri(), " ";
                if($_obj)
                {
                    //echo $_obj->getUri();
                    $ovalue = $_obj;
                }
                else
                {
                    $omap = $kv->get("rr:objectMap");

                    $const = $omap->get("rr:constant");
                    $otpl = $omap->get("rr:template");
                    $oref = $omap->get("rml:reference");
                    $dtype = $omap->get("rr:datatype");
                    $ttype = $omap->get("rr:termType");
                    $lang = $omap->get("rr:language");
                    $join = $omap->get("rr:parentTriplesMap");
                    $ovalue = null;
                
                
                    if($const)
                    {
                        $ovalue = $const;
                    }
                    
                    if($otpl)
                    {
                        //echo "tpl:", $otpl, " ";
                        $tvars = extract_vars($otpl);
                        $tmp = $otpl;
                        foreach($tvars as $k => $var){
                            $val = $format_reader->lookup($var, $obj);
                            if(is_array($val))
                                $val = $val[0];
                            $tmp = str_replace("{".$var."}", $val, $tmp);
                        }
                        $ovalue = $tmp;
                    }
                    
                    if($oref)
                    {
                        #echo "ref:", $oref, " ";
                        #print_r($oref);
                        if(is_object($oref))
                            $oref = $oref->getValue();
                        $val = $format_reader->lookup($oref, $obj);
                        $ovalue = array();
                        if(is_array($val)){
                            foreach($val as $vv => $_v)
                                $ovalue[] = "".$_v;
                        }
                        else
                            $ovalue[] = $val;
                    }
                    
                    if($join)
                    {
                        //echo "join: ";
                        $ttype = _exp("rr:IRI");
                        $jc = $omap->all("rr:joinCondition");
                        $jval = array();
                        foreach($jc as $k => $v)
                        {
                            $parent = $v->get("rr:parent");
                            $child = $v->get("rr:child")->getValue();
                            $val = $format_reader->lookup($child, $obj);
                            if(is_array($val)){
                                $cval = array();
                                foreach($val as $vv => $_v) $cval[] = "".$_v;
                            }
                            else
                                $cval = "".$val;

                            $jval[$parent->getValue()] = $cval;
                        }

                        $ovalue = array();
                        foreach($lookup[$join->getUri()][$mapuri] as $k => $pv)
                        {
                            $match = true;
                            foreach($jval as $key => $kval)
                            {
                                $vmatch = false;
                                if(is_array($kval)){
                                    foreach($kval as $kk => $kv)
                                        if($kv==$pv[0][$key]){
                                            $vmatch = true;
                                            break;
                                        }
                                    if(!$vmatch){
                                        $match = false;
                                        break;
                                    }
                                }
                                else
                                    if($pv[0][$key]!=$kval){
                                        $match = false;
                                        break;
                                    }
                            }
                            if($match){
                                $ovalue[] = $pv[1];
                            }
                        }
                    }
                }

                if ($ovalue==null) continue;


                if(!is_array($ovalue))
                    $ovalue = array($ovalue);

                foreach($ovalue as $k => $value)
                {
                    if($ttype)
                    {
                        switch($ttype)
                        {
                            case _exp("rr:IRI"):
                                $value = $output->resource($value);
                                break; 

                            case _exp("rr:Literal"):
                                if($dtype)
                                {
                                    $value = EasyRdf_Literal::create($value, $lang, $dtype);
                                }
                                break;
                        }
                    }
                    else if($dtype)
                    {
                        $value = EasyRdf_Literal::create($value, $lang, $dtype);
                    }
                    #echo "\t", $pred->getUri(), " ", $value,"\n";
                    $output->add($subj, $pred, $value);
                }
                
            }
        }
        //if(array_key_exists($mapuri, $lookup)) print_r($lookup[$mapuri]);
    }
    $format = EasyRdf_Format::getFormat("n3");
    $output = $output->serialise($format);
    echo $output;
});

route('/test/rmlbibtex', function($arg){
    header("content-type: text/plain");
    $bib = new Structures_BibTex();
    $bib->loadFile("tmp/citations.bib");
    $bib->parse();
    print_r($bib->data);
    $json = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
    $tmp = $json->encode($bib->data);
    $jdata = $json->decode($tmp);
    echo "--";
    //print_r(jsonPath($bib->data, "$.author"));
    print_r(jsonPath($jdata, "$..author[*]"));
});

?>