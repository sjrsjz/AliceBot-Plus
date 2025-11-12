let maybe_pkg: any = import "maybe.mu";
let List: any = T: any => rec list: (() | T @ list);
let Nil: any = ();
let cons: any = (head: any, tail: any) => (head,) + tail;
let head: any = match
    | (h: any) @ _ => h
    | panic;
let tail: any = match
    | _ @ (t: any) => t
    | panic;
let is_nil: any = match
    | () => true
    | _ => false
    | panic;
let iter: any = lst: List(any) => f: any => {
    loop go: t: any = lst;
    match t
        | () => ()
        | (h: any) @ (t: any) => {
            discard f(h);
            go(t)
        }
        | panic
};
let map: any = lst: List(any) => f: any => {
    loop go: t: any = lst;
    match t
        | () => ()
        | (h: any) @ (t: any) => cons(f(h), go(t))
        | panic
};
let len: any = lst: List(any) => {
    loop go: t: any = lst;
    match t
        | () => 0
        | _ @ (t: any) => 1 + go(t)
        | panic
};
let filter: any = lst: List(any) => pred: any => {
    loop go: t: any = lst;
    match t
        | () => ()
        | (h: any) @ (t: any) => if pred(h)
            then cons(h, go(t))
            else go(t)
        | panic
};
let fold: any = lst: List(any) => acc: any => f: any => {
    loop go: t: any = (lst, acc);
    match t
        | ((), a: any) => a
        | ((h: any) @ (t: any), a: any) => go(t, f(a, h))
        | panic
};
let foldr: any = lst: List(any) => acc: any => f: any => {
    loop go: t: any = lst;
    match t
        | () => acc
        | (h: any) @ (t: any) => f(h, go(t))
        | panic
};
let append: any = lst1: List(any) => lst2: List(any) => {
    lst1 + lst2
};
let reverse: any = lst: List(any) => {
    loop go: t: any = (lst, ());
    match t
        | ((), acc: any) => acc
        | ((h: any) @ (t: any), acc: any) => go(t, cons(h, acc))
        | panic
};
let nth: any = lst: List(any) => n: int => {
    loop go: (t: any, i: int) = (lst, n);
    match (t, i)
        | ((h: any) @ _, eq 0) => h
        | (_ @ (t: any), i: int) => go(t, i - 1)
        | panic
};
let take: any = lst: List(any) => n: int => {
    loop go: (t: any, i: int) = (lst, n);
    match (t, i)
        | ((), _) => ()
        | (_, eq 0) => ()
        | ((h: any) @ (t: any), i: int) => cons(h, go(t, i - 1))
        | panic
};
let drop: any = lst: List(any) => n: int => {
    loop go: (t: any, i: int) = (lst, n);
    match (t, i)
        | ((), _) => ()
        | (l: any, eq 0) => l
        | (_ @ (t: any), i: int) => go(t, i - 1)
        | panic
};
let find: any = lst: List(any) => pred: any => {
    let go: any = rec go: match
        | () => {
            let Nothing::(v: any) = maybe_pkg;
            v
        }
        | (h: any) @ (t: any) => if pred(h)
            then {
                let Just::(v: any) = maybe_pkg;
                v(h)
            }
            else go(t)
        | panic;
    go(lst)
};
let list_all: any = lst: List(any) => pred: any => {
    let go: any = rec go: match
        | () => true
        | (h: any) @ (t: any) => if pred(h)
            then go(t)
            else false
        | panic;
    go(lst)
};
let list_any: any = lst: List(any) => pred: any => {
    let go: any = rec go: match
        | () => false
        | (h: any) @ (t: any) => if pred(h)
            then true
            else go(t)
        | panic;
    go(lst)
};

List::List &
Nil::Nil &
cons::cons &
head::head &
tail::tail &
is_nil::is_nil &
iter::iter &
map::map &
len::len &
filter::filter &
fold::fold &
foldr::foldr &
append::append &
reverse::reverse &
nth::nth &
take::take &
drop::drop &
find::find &
list_all::list_all &
list_any::list_any