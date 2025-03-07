Z := (f => (x => null) -> { return x(x); }) -> {
    return f((x => null, f => f) -> {
        return f(Z(f))(x);
    });
};

lazy := (computation => null) -> {
    result := null;
    evaluated := false;
    
    return (evaluated => evaluated,
            result => result,
            computation => computation) -> {
        if (evaluated == false) {
            result = computation();
            evaluated = true;
        };
        return result;
    };
};

mutistr := (str => "", n => 0) -> {
    result := "";

    i := 0; while (i = i + 1; i <= n) {
        result = result + str;
    };

    return result;
};

loop := (func => (n => 0) -> {return false}) -> {
    return (n => 0, func => func) -> {
        while (func(n)) {
            n = n + 1;
        };      
    };
};


iter := (container => ('T' : null), n => 0) -> {
    n = n + 1;
    E := valueof container;
    T := keyof container;
    if (n <= len(T)) {
        (deref E) = T[n - 1];
        return true;
    } else {
        return false;
    };
};


// 创建一个关系表结构
// 支持列定义、数据插入、查询、更新和删除
RelationTable := (columns => ()) -> {
    return (
        // 表结构定义
        'columns': columns,
        'rows': (),
        
        // 插入一行数据
        insert => (row => ()) -> {
            // 验证行数据与列定义匹配
            if (len(row) != len(self.columns)) {
                print("错误: 数据列数与表结构不匹配");
                return false;
            };
            
            // 添加到行集合中
            self.rows = self.rows + (row,);
            return true;
        },
        
        // 查找满足条件的行
        select => (condition => (row => null) -> { return true; }) -> {
            result := ();
            i := 0;
            while (i < len(self.rows)) {
                if (condition(self.rows[i])) {
                    result = result + (self.rows[i],);
                };
                i = i + 1;
            };
            return result;
        },
        
        // 更新满足条件的行
        update => (condition => (row => null) -> { return false; }, 
                   updater => (row => null) -> { return row; }) -> {
            count := 0;
            i := 0;
            while (i < len(self.rows)) {
                if (condition(self.rows[i])) {
                    self.rows[i] = updater(self.rows[i]);
                    count = count + 1;
                };
                i = i + 1;
            };
            return count;
        },
        
        // 删除满足条件的行
        delete => (condition => (row => null) -> { return false; }) -> {
            newRows := ();
            count := 0;
            i := 0;
            while (i < len(self.rows)) {
                if (condition(self.rows[i])) {
                    count = count + 1;
                } else {
                    newRows = newRows + (self.rows[i],);
                };
                i = i + 1;
            };
            self.rows = newRows;
            return count;
        },
        
        // 获取列索引
        getColumnIndex => (columnName => "") -> {
            i := 0;
            while (i < len(self.columns)) {
                if (self.columns[i] == columnName) {
                    return i;
                };
                i = i + 1;
            };
            return -1;
        },
        
        // 根据列名获取列值
        getColumnValue => (row => (), columnName => "") -> {
            index := self.getColumnIndex(columnName);
            if (index < 0) {
                return null;
            };
            return row[index];
        },
        
        // 排序结果集
        sort => (rows => (), columnName => "", ascending => true) -> {
            // 简单实现冒泡排序
            index := self.getColumnIndex(columnName);
            if (index < 0) {
                return rows;
            };
            
            result := rows;
            i := 0;
            while (i < len(result)) {
                j := 0;
                while (j < len(result) - i - 1) {
                    shouldSwap := false;
                    if (ascending) {
                        shouldSwap = result[j][index] > result[j+1][index];
                    } else {
                        shouldSwap = result[j][index] < result[j+1][index];
                    };
                    
                    if (shouldSwap) {
                        temp := result[j];
                        result[j] = result[j+1];
                        result[j+1] = temp;
                    };
                    j = j + 1;
                };
                i = i + 1;
            };
            
            return result;
        },
        
        // 打印表格
        display => (rows => null) -> {
            rowsToShow := rows;
            if (rowsToShow == null) {
                print("显示所有数据:");
                rowsToShow = self.rows;
            };
            // 打印表头
            i := 0;
            while (i < len(self.columns)) {
                print(self.columns[i]);
                i = i + 1;
            };
            
            // 打印数据行
            i = 0;
            while (i < len(rowsToShow)) {
                row := rowsToShow[i];
                j := 0;
                while (j < len(row)) {
                    print(row[j]);
                    j = j + 1;
                };
                print("");
                i = i + 1;
            };
        }
    );
};


html := (tag => "", attrs => (), children => ()) -> {
    buildAttrs := () -> {
        result := "";
        i := 0;
        while (i < len(attrs)) {
            attr := attrs[i];
            result = result + " " + keyof attr + "=\"" + valueof attr + "\"";
            i = i + 1;
        };
        return result;
    };
    
    buildChildren := () -> {
        result := "";
        i := 0;
        while (i < len(children)) {
            result = result + children[i];
            i = i + 1;
        };
        return result;
    };
    
    if (len(children) == 0) {
        return "<" + tag + buildAttrs() + "/>";
    } else {
        return "<" + tag + buildAttrs() + ">" + buildChildren() + "</" + tag + ">";
    };
};

htmlpkg := (
    // 创建常用HTML标签函数
    div => (attrs => (), children => (), html => html) -> { return html("div", attrs, children); },
    span => (attrs => (), children => (), html => html) -> { return html("span", attrs, children); },
    h1 => (attrs => (), children => (), html => html) -> { return html("h1", attrs, children); },
    h2 => (attrs => (), children => (), html => html) -> { return html("h2", attrs, children); },
    h3 => (attrs => (), children => (), html => html) -> { return html("h3", attrs, children); },
    h4 => (attrs => (), children => (), html => html) -> { return html("h4", attrs, children); },
    h5 => (attrs => (), children => (), html => html) -> { return html("h5", attrs, children); },
    h6 => (attrs => (), children => (), html => html) -> { return html("h6", attrs, children); },
    p => (attrs => (), children => (), html => html) -> { return html("p", attrs, children); },
    a => (attrs => (), children => (), html => html) -> { return html("a", attrs, children); },
    img => (attrs => (), children => (), html => html) -> { return html("img", attrs, children); },
    input => (attrs => (), children => (), html => html) -> { return html("input", attrs, children); },
    button => (attrs => (), children => (), html => html) -> { return html("button", attrs, children); },
    form => (attrs => (), children => (), html => html) -> { return html("form", attrs, children); },
    label => (attrs => (), children => (), html => html) -> { return html("label", attrs, children); },
    table => (attrs => (), children => (), html => html) -> { return html("table", attrs, children); },
    tr => (attrs => (), children => (), html => html) -> { return html("tr", attrs, children); },
    th => (attrs => (), children => (), html => html) -> { return html("th", attrs, children); },
    td => (attrs => (), children => (), html => html) -> { return html("td", attrs, children); },
    ul => (attrs => (), children => (), html => html) -> { return html("ul", attrs, children); },
    ol => (attrs => (), children => (), html => html) -> { return html("ol", attrs, children); },
    li => (attrs => (), children => (), html => html) -> { return html("li", attrs, children); },
    hr => (attrs => (), children => (), html => html) -> { return html("hr", attrs, children); },
    br => (attrs => (), children => (), html => html) -> { return html("br", attrs, children); },
    meta => (attrs => (), children => (), html => html) -> { return html("meta", attrs, children); },
    link => (attrs => (), children => (), html => html) -> { return html("link", attrs, children); },
    style => (attrs => (), children => (), html => html) -> { return html("style", attrs, children); },
    script => (attrs => (), children => (), html => html) -> { return html("script", attrs, children); },
    head => (attrs => (), children => (), html => html) -> { return html("head", attrs, children); },
    body => (attrs => (), children => (), html => html) -> { return html("body", attrs, children); },
    html => (attrs => (), children => (), html => html) -> { return html("html", attrs, children); }
)


return (
    Z => Z,
    lazy => lazy,
    mutistr => mutistr,
    loop => loop,
    iter => iter,
    RelationTable => RelationTable,
    htmlpkg => htmlpkg,
    html => html,
)
