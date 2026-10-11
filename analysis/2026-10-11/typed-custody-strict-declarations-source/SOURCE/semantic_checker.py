"""Bounded offline draft-07 subset for pinned native request schemas.

No schema fetching, imports of target code, defaults, coercion or RPC.
Unknown reached assertion keywords/formats refuse; schema validity is no grant.
Numeric formats are separate protocol annotation checks, enabled by default.
"""
import json
import math
import re
import posixpath


class Refusal(ValueError):
    def __init__(self, code, path="$", detail=""):
        self.code, self.path, self.detail = code, path, detail
        super().__init__(code + " at " + path + (": " + detail if detail else ""))


def finite(value, max_nodes=50000, max_depth=64):
    stack = [(value, 0, "$")]; count = 0
    while stack:
        v, depth, path = stack.pop(); count += 1
        if count > max_nodes: raise Refusal("JSON_NODE_BOUND", path)
        if depth > max_depth: raise Refusal("JSON_DEPTH_BOUND", path)
        if v is None or type(v) in (bool, int): continue
        if type(v) is float:
            if not math.isfinite(v): raise Refusal("JSON_NONFINITE", path)
        elif type(v) is str:
            try: v.encode("utf-8", "strict")
            except UnicodeError: raise Refusal("JSON_UNICODE", path)
        elif type(v) is list:
            stack.extend((x, depth+1, path+"/"+str(i)) for i,x in enumerate(v))
        elif type(v) is dict:
            for k,x in v.items():
                if type(k) is not str: raise Refusal("JSON_KEY_TYPE", path)
                try: k.encode("utf-8", "strict")
                except UnicodeError: raise Refusal("JSON_UNICODE", path)
                stack.append((x,depth+1,path+"/"+k.replace("~","~0").replace("/","~1")))
        else: raise Refusal("JSON_TYPE", path)
    return count


def strict_loads(raw, max_bytes=16*1024*1024, max_nodes=50000, max_depth=64):
    if type(raw) not in (str, bytes): raise Refusal("JSON_INPUT_TYPE")
    try:
        if type(raw) is bytes: raw = raw.decode("utf-8", "strict")
        if len(raw.encode("utf-8", "strict")) > max_bytes: raise Refusal("JSON_BYTE_BOUND")
        def pairs(items):
            d = {}
            for k,v in items:
                if k in d: raise Refusal("JSON_DUPLICATE_KEY", "$", k)
                d[k] = v
            return d
        def constant(v): raise Refusal("JSON_NONFINITE", "$", v)
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Refusal: raise
    except (ValueError, UnicodeError, RecursionError, OverflowError) as e:
        raise Refusal("JSON_PARSE", "$", type(e).__name__) from None
    finite(value,max_nodes,max_depth)
    return value


def equal(a,b):
    # bool is distinct from number; JSON numeric equality treats 1 and 1.0 alike.
    if type(a) is bool or type(b) is bool: return type(a) is type(b) and a==b
    if type(a) is dict and type(b) is dict:
        return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if type(a) is list and type(b) is list:
        return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b


class Checker:
    annotations = {"$schema","$id","definitions","$defs","title","description","default","examples","readOnly","writeOnly","deprecated"}
    assertions = {"$ref","type","enum","const","properties","required","additionalProperties","items","oneOf","anyOf","allOf","not","minimum","maximum","exclusiveMinimum","exclusiveMaximum","minLength","maxLength","minItems","maxItems","uniqueItems","minProperties","maxProperties","pattern","format"}
    integer_formats = {"int64":(-2**63,2**63-1),"int32":(-2**31,2**31-1),"uint64":(0,2**64-1),"uint32":(0,2**32-1),"uint16":(0,2**16-1)}

    def __init__(self, documents, max_steps=50000, max_depth=64, protocol_formats=True):
        self.documents=documents; self.max_steps=max_steps;self.max_depth=max_depth
        self.protocol_formats=protocol_formats; self.steps=0; self.visited=set()

    def resolve(self, file, ref):
        if type(ref) is not str or ref.count("#")>1: raise Refusal("REF_SYNTAX")
        name, _, fragment = ref.partition("#")
        if name:
            if name.startswith("/") or ":" in name or "\\" in name or ".." in name.split("/"):
                raise Refusal("REF_EXTERNAL_OR_TRAVERSAL", "$", ref)
            file=posixpath.normpath(posixpath.join(posixpath.dirname(file),name))
        if file not in self.documents: raise Refusal("REF_UNBOUND", "$", file)
        node=self.documents[file]
        if fragment:
            if not fragment.startswith("/") or "%" in fragment: raise Refusal("REF_POINTER_SYNTAX", "$", ref)
            try:
                for key in fragment[1:].split("/"):
                    if re.search(r"~(?![01])",key): raise Refusal("REF_POINTER_SYNTAX", "$", ref)
                    key=key.replace("~1","/").replace("~0","~")
                    node=node[int(key)] if type(node) is list and key.isdigit() else node[key]
            except Refusal: raise
            except (KeyError,IndexError,TypeError,ValueError): raise Refusal("REF_UNBOUND", "$", ref) from None
        return file,node

    @staticmethod
    def is_type(v,t):
        return {"null":v is None,"boolean":type(v) is bool,"object":type(v) is dict,
                "array":type(v) is list,"string":type(v) is str,
                "number":type(v) in (int,float),
                "integer":type(v) is int or (type(v) is float and math.isfinite(v) and v.is_integer())}.get(t,False)

    def check(self,value,schema,file="ClientRequest.json"):
        finite(value); self.steps=0;self.visited=set()
        self._declarations(schema, file)
        self._check(value,schema,file,"$",0,set())
        return {"valid":True,"steps":self.steps,"schema_nodes_visited":len(self.visited),"admission":False}

    def _declarations(self, schema, file):
        """Refuse malformed declarations before value-dependent branches.

        This remains the supported offline subset, with no schema fetching.
        Walk local references once; actual value/ref recursion is still checked
        by _check. Validation does not cache mutable schema objects across calls.
        """
        todo = [(schema, file, "$", 0)]
        seen = set()
        steps = 0
        while todo:
            s, file, path, depth = todo.pop()
            key = (file, id(s))
            if key in seen:
                continue
            seen.add(key)
            steps += 1
            if steps > self.max_steps:
                raise Refusal("SCHEMA_STEP_BOUND", path)
            if depth > self.max_depth:
                raise Refusal("SCHEMA_DEPTH_BOUND", path)
            if type(s) is bool:
                continue
            if type(s) is not dict:
                raise Refusal("SCHEMA_NODE_TYPE", path)
            finite(s)
            unknown = set(s) - self.annotations - self.assertions
            if unknown:
                raise Refusal("SCHEMA_UNSUPPORTED", path, ",".join(sorted(unknown)))
            if "type" in s:
                ts = [s["type"]] if type(s["type"]) is str else s["type"]
                if (type(ts) is not list or not ts or
                    any(type(t) is not str or t not in ("null", "boolean", "object", "array", "string", "number", "integer") for t in ts) or
                    len(set(ts)) != len(ts)):
                    raise Refusal("SCHEMA_TYPE_DECLARATION", path)
            if "enum" in s:
                enum = s["enum"]
                if (type(enum) is not list or not enum or
                    any(equal(x, y) for i, x in enumerate(enum) for y in enum[:i])):
                    raise Refusal("SCHEMA_ENUM_DECLARATION", path)
            if "required" in s:
                required = s["required"]
                if (type(required) is not list or
                    any(type(k) is not str for k in required) or
                    len(set(required)) != len(required)):
                    raise Refusal("SCHEMA_REQUIRED_DECLARATION", path)
            for name in ("properties", "definitions", "$defs"):
                if name in s:
                    if type(s[name]) is not dict:
                        raise Refusal("SCHEMA_PROPERTIES_DECLARATION", path, name)
                    for name_key, child in s[name].items():
                        todo.append((child, file, path + "/" + name + "/" + name_key, depth + 1))
            for name in ("additionalProperties", "items", "not"):
                if name in s:
                    if name == "items" and type(s[name]) is list:
                        raise Refusal("SCHEMA_UNSUPPORTED_TUPLE_ITEMS", path)
                    todo.append((s[name], file, path + "/" + name, depth + 1))
            for name in ("oneOf", "anyOf", "allOf"):
                if name in s:
                    branches = s[name]
                    if type(branches) is not list or not branches:
                        raise Refusal("SCHEMA_UNION_DECLARATION", path)
                    todo.extend((child, file, path + "/" + name + "/" + str(i), depth + 1) for i, child in enumerate(branches))
            for name in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
                if name in s and type(s[name]) not in (int, float):
                    raise Refusal("SCHEMA_NUMERIC_DECLARATION", path, name)
            for name in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
                if name in s and (type(s[name]) is not int or s[name] < 0):
                    raise Refusal("SCHEMA_LENGTH_DECLARATION", path, name)
            for name in ("uniqueItems", "readOnly", "writeOnly", "deprecated"):
                if name in s and type(s[name]) is not bool:
                    raise Refusal("SCHEMA_BOOLEAN_DECLARATION", path, name)
            for name in ("$schema", "$id", "title", "description", "format"):
                if name in s and type(s[name]) is not str:
                    raise Refusal("SCHEMA_STRING_DECLARATION", path, name)
            if "examples" in s and type(s["examples"]) is not list:
                raise Refusal("SCHEMA_EXAMPLES_DECLARATION", path)
            if "pattern" in s:
                if type(s["pattern"]) is not str:
                    raise Refusal("SCHEMA_PATTERN_DECLARATION", path)
                try:
                    re.compile(s["pattern"])
                except (re.error, RecursionError, OverflowError):
                    raise Refusal("SCHEMA_PATTERN_DECLARATION", path) from None
            if "$ref" in s:
                next_file, target = self.resolve(file, s["$ref"])
                todo.append((target, next_file, path + "/$ref", depth + 1))

    def _check(self,v,s,file,path,depth,chain):
        self.steps+=1
        if self.steps>self.max_steps: raise Refusal("SCHEMA_STEP_BOUND",path)
        if depth>self.max_depth: raise Refusal("SCHEMA_DEPTH_BOUND",path)
        self.visited.add((file,id(s)))
        if s is True: return
        if s is False: raise Refusal("FALSE_SCHEMA",path)
        if type(s) is not dict: raise Refusal("SCHEMA_NODE_TYPE",path)
        unknown=set(s)-self.annotations-self.assertions
        if unknown: raise Refusal("SCHEMA_UNSUPPORTED",path,",".join(sorted(unknown)))
        if "$ref" in s:
            # Draft-07: siblings of $ref are ignored, not applied as assertions.
            nf,ns=self.resolve(file,s["$ref"]); key=(nf,id(ns),path)
            if key in chain: raise Refusal("REF_CYCLE",path)
            self._check(v,ns,nf,path,depth+1,chain|{key});return
        types=s.get("type")
        if types is not None:
            types=[types] if type(types) is str else types
            if type(types) is not list or not types or any(t not in ("null","boolean","object","array","string","number","integer") for t in types): raise Refusal("SCHEMA_TYPE_DECLARATION",path)
            if not any(self.is_type(v,t) for t in types): raise Refusal("TYPE",path,"expected "+str(types))
        if "enum" in s and not any(equal(v,x) for x in s["enum"]): raise Refusal("ENUM",path)
        if "const" in s and not equal(v,s["const"]): raise Refusal("CONST",path)
        for union in ("oneOf","anyOf","allOf"):
            if union not in s:continue
            branches=s[union]
            if type(branches) is not list or not branches: raise Refusal("SCHEMA_UNION_DECLARATION",path)
            matches=0;errors=[]
            for branch in branches:
                try:self._check(v,branch,file,path,depth+1,chain);matches+=1
                except Refusal as e:
                    if e.code.startswith(("SCHEMA_","REF_")):raise
                    errors.append({"code":e.code,"path":e.path})
            valid=(matches==1 if union=="oneOf" else matches>=1 if union=="anyOf" else matches==len(branches))
            if not valid: raise Refusal(union.upper(),path,json.dumps({"matches":matches,"branches":len(branches),"first_errors":errors[:5]},sort_keys=True))
        if "not" in s:
            try:self._check(v,s["not"],file,path,depth+1,chain)
            except Refusal as e:
                if e.code.startswith(("SCHEMA_","REF_")):raise
            else:raise Refusal("NOT",path)
        if type(v) is dict:
            props=s.get("properties",{}); required=s.get("required",[])
            for k in required:
                if k not in v:raise Refusal("REQUIRED",path+"/"+k)
            for k,x in v.items():
                sub=props.get(k,s.get("additionalProperties",True))
                self._check(x,sub,file,path+"/"+k.replace("~","~0").replace("/","~1"),depth+1,chain)
            if len(v)<s.get("minProperties",0):raise Refusal("MIN_PROPERTIES",path)
            if "maxProperties" in s and len(v)>s["maxProperties"]:raise Refusal("MAX_PROPERTIES",path)
        if type(v) is list:
            if len(v)<s.get("minItems",0):raise Refusal("MIN_ITEMS",path)
            if "maxItems" in s and len(v)>s["maxItems"]:raise Refusal("MAX_ITEMS",path)
            if s.get("uniqueItems") and any(equal(x,y) for i,x in enumerate(v) for y in v[:i]):raise Refusal("UNIQUE_ITEMS",path)
            if "items" in s:
                if type(s["items"]) is list:raise Refusal("SCHEMA_UNSUPPORTED_TUPLE_ITEMS",path)
                for i,x in enumerate(v):self._check(x,s["items"],file,path+"/"+str(i),depth+1,chain)
        if type(v) is str:
            if len(v)<s.get("minLength",0):raise Refusal("MIN_LENGTH",path)
            if "maxLength" in s and len(v)>s["maxLength"]:raise Refusal("MAX_LENGTH",path)
            if "pattern" in s and re.search(s["pattern"],v) is None:raise Refusal("PATTERN",path)
        if type(v) in (int,float):
            for k,op in (("minimum",lambda a,b:a>=b),("maximum",lambda a,b:a<=b),("exclusiveMinimum",lambda a,b:a>b),("exclusiveMaximum",lambda a,b:a<b)):
                if k in s and not op(v,s[k]):raise Refusal(k.upper(),path)
        if "format" in s and v is not None:
            f=s["format"]
            if f not in self.integer_formats and f not in ("uint","double"):raise Refusal("SCHEMA_UNSUPPORTED_FORMAT",path,f)
            if self.protocol_formats:
                if f in self.integer_formats:
                    lo,hi=self.integer_formats[f]
                    if type(v) is not int or not lo<=v<=hi:raise Refusal("PROTOCOL_INTEGER_FORMAT",path,f)
                elif f=="uint":
                    # Pointer-width dependent upper bound cannot be inferred offline.
                    if type(v) is not int or v<0:raise Refusal("PROTOCOL_UINT_FORMAT",path)
                elif type(v) not in (int,float):raise Refusal("PROTOCOL_DOUBLE_FORMAT",path)

    def branch(self,method):
        root=self.documents["ClientRequest.json"]
        matches=[x for x in root.get("oneOf",[]) if x.get("properties",{}).get("method",{}).get("enum")==[method]]
        if len(matches)!=1:raise Refusal("METHOD_UNDECLARED_OR_AMBIGUOUS", "$/method",method)
        return matches[0]

    def request(self,method,params,request_id=1):
        finite({"id":request_id,"method":method,"params":params})
        return self.check({"id":request_id,"method":method,"params":params},self.branch(method))
