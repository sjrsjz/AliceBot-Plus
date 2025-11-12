let list_pkg: any = import "list.mu";
let maybe_pkg: any = import "maybe.mu";
let List::(List: any) = list_pkg;
let iter::(iter: any) = list_pkg;
let len::(len: any) = list_pkg;
let take::(take: any) = list_pkg;
let drop::(drop: any) = list_pkg;
let Just::(Just: any) = maybe_pkg;
let Nothing::(Nothing: any) = maybe_pkg;

let String: any = List(char);

let println: any = s: String => {
    discard iter(s)(c: char => {
        discard put!(c);
    });
    discard put!('\n');
};

let print: any = s: String => {
    discard iter(s)(c: char => {
        discard put!(c);
    });
};

let slice: any = (s: String, start: int, end: int) => {
    let len: int = len(s);
    if (start >= 0 && start <= len && end >= start && end <= len)
        then Just(take(drop(s)(start))(end - start))
        else Nothing
};

let int_to_string: any = rec f: n: int => {
    if n < 0 then "-" + f(-n)
    else match n
        | eq 0 => "0"
        | _ => {
            loop go: (acc: String, n: int) = ((), n);
                if n == 0 then acc
                else {
                    let digit: (char,) = match n % 10
                        | eq 0 => "0"
                        | eq 1 => "1"
                        | eq 2 => "2"
                        | eq 3 => "3"
                        | eq 4 => "4"
                        | eq 5 => "5"
                        | eq 6 => "6"
                        | eq 7 => "7"
                        | eq 8 => "8"
                        | eq 9 => "9"
                        | panic;
                    go((digit + acc, n / 10))
                }
        }
        | panic
};

String::String &
println::println &
print::print &
slice::slice &
int_to_string::int_to_string