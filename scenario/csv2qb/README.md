# CSV2QB

sample test case to convert CSV into Cube Model (qb:)

the mapping description is in the .jsonld file. the vocabulary for mapping is ad-hoc and is written in the context

the mapping has three parts : 
- source description: 
- global map : one-time manual
- content mapping : maps content described in the source
- post processing : ordered process to transform on generated triples from previous process (global and content map)

current implementation of the mapping only reads the file from local file and reading the source via native csv DictReader.

these code below is the implementation of external service that is written in the [https://github.com/pebbie/botol](botol) microframework. 

the namespace for the properties is http://pebbie.org/ont/autotome/ (not yet dereference-able)

```php
//simple service to convert string into a slug (replace whitespace with dash and transform to lowercase)
route('/services/slugification', function($arg){
    $tmp = $_GET["input"];
    $prefix = isset($_GET["prefix"])?$_GET["prefix"]:"";
    echo $prefix.str_replace(" ", "-", strtolower($tmp));
});

//simple web service to generate unique string
route('/services/genuri', function($arg){
    $prefix = isset($_GET["prefix"])?$_GET["prefix"]:"";
    echo uniqid($prefix);
});
```