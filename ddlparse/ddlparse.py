# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Shinichi Takii, shinichi.takii@gmail.com
#
# This module is part of python-ddlparse and is released under
# the BSD License: https://opensource.org/licenses/BSD-3-Clause

"""Parse DDL statements"""

import re
from collections import OrderedDict
from enum import IntEnum

from pyparsing import CaselessKeyword, Forward, Word, Regex, alphanums, unicodeString, \
    delimitedList, Suppress, Optional, Group, OneOrMore


class DdlParseBase():

    NAME_CASE = IntEnum("NAME_CASE", "original lower upper")

    def __init__(self):
        pass


class DdlParseTableColumnBase(DdlParseBase):

    def __init__(self):
        super().__init__()
        self._name = ""

    @property
    def name(self):
        """name"""
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def _get_name(self, name_case=DdlParseBase.NAME_CASE.original):
        """
        Get Name converted case

        :param name_case: name case type
            * NAME_CASE.original : Return to no convert
            * NAME_CASE.lower : Return to lower
            * NAME_CASE.upper : Return to upper

        :return: name
        """
        if name_case == self.NAME_CASE.lower:
            return self._name.lower()
        elif name_case == self.NAME_CASE.upper:
            return self._name.upper()
        else:
            return self._name


class DdlParseColumn(DdlParseTableColumnBase):
    """Column define info"""

    def __init__(self, name, data_type_array, constraint=None):
        """
        :param data_type_array[]: Column data type [data type name, length, precision]
        :param constraint: Column constraint string
        """
        super().__init__()
        self._name = name
        self._set_data_type(data_type_array)
        self.constraint = constraint

    @property
    def data_type(self):
        return self._data_type

    @property
    def length(self):
        return self._length

    @property
    def precision(self):
        return self._length

    @property
    def scale(self):
        return self._scale

    def _set_data_type(self, data_type_array):
        self._data_type = data_type_array[0].upper()
        self._length = None
        self._scale = None

        if len(data_type_array) < 2:
            return

        matches = re.findall(r"(\d+)\s*,*\s*(\d*)", data_type_array[1])
        if len(matches) > 0:
            self._length = int(matches[0][0])
            self._scale = None if len(matches[0]) < 2 or matches[0][1] == "" or int(matches[0][1]) == 0 else int(matches[0][1])
        else:
            self._data_type += " {}".format(data_type_array[1])


    @property
    def constraint(self):
        """Constraint string"""
        constraint_arr = []
        if self._not_null:
            constraint_arr.append("PRIMARY KEY" if self._pk else "NOT NULL")
        if self._unique:
            constraint_arr.append("UNIQUE")

        return " ".join(constraint_arr)

    @constraint.setter
    def constraint(self, constraint):
        self._constraint = None if constraint is None else constraint.upper()

        self._not_null = False if self._constraint is None or not re.search(r"(NOT NULL|PRIMARY KEY)", self._constraint) else True
        self._pk = False if self._constraint is None or not re.search("PRIMARY KEY", self._constraint) else True
        self._unique = False if self._constraint is None or not re.search("UNIQUE", self._constraint) else True

    @property
    def not_null(self):
        return self._not_null

    @not_null.setter
    def not_null(self, flag):
        self._not_null = flag

    @property
    def primary_key(self):
        return self._pk

    @primary_key.setter
    def primary_key(self, flag):
        self._pk = flag

    @property
    def unique(self):
        return self._unique

    @unique.setter
    def unique(self, flag):
        self._unique = flag

    @property
    def bigquery_data_type(self):
        """Get BigQuery data type"""

        BQ_DATA_TYPE_DIC = {
            # BigQuery data type : [condition, ...]
            "STRING" : [re.compile(r"(CHAR|TEXT)")],
            "INTEGER" : [re.compile(r"INT|SERIAL|YEAR")],
            "FLOAT" : [re.compile(r"(FLOAT|DOUBLE)"), "REAL", "MONEY"],
            "DATE" : ["DATE"],
            "TIME" : ["TIME"],
            "DATETIME" : ["DATETIME", "TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE"],
            "TIMESTAMP" : ["TIMESTAMPTZ", "TIMESTAMP WITH TIME ZONE"],
            "BOOLEAN" : [re.compile(r"BOOL")],
            }

        this_bq_type = None

        for bq_type, conditions in BQ_DATA_TYPE_DIC.items():
            for condition in conditions:
                if isinstance(condition, str):
                    if self._data_type == condition:
                        this_bq_type = bq_type
                        break
                elif re.search(condition, self._data_type):
                    this_bq_type = bq_type
                    break

        if this_bq_type is None:
            if self._data_type in ["NUMERIC", "DECIMAL"]:
                this_bq_type = "INTEGER" if self._scale is None else "FLOAT"
            else:
                raise ValueError("Unknown data type : '{}'".format(self._data_type))

        return this_bq_type

    @property
    def bigquery_mode(self):
        """Get BigQuery constraint"""

        return "REQUIRED" if self.not_null else "NULLABLE"

    def to_bigquery_field(self, name_case=DdlParseBase.NAME_CASE.original):
        """Generate BigQuery JSON field define"""

        return '{{"name": "{}", "type": "{}", "mode": "{}"}}'.format(self._get_name(name_case), self.bigquery_data_type, self.bigquery_mode)


class DdlParseColumnDict(OrderedDict):
    """
    Columns dictionary collection

    * Orderd dictionary
    * Dict with case insensitive keys
      (SQL is case insensitive)
    """

    def __init__(self):
        super().__init__()

    def __getitem__(self, key):
        return super().__getitem__(key.lower())

    def __setitem__(self, key, value):
        super().__setitem__(key.lower(), value)

    def append(self, column_name, data_type_array=None, constraint=None):
        column = DdlParseColumn(column_name, data_type_array, constraint)
        self.__setitem__(column_name, column)
        return column


class DdlParseTable(DdlParseTableColumnBase):
    """Table define info"""

    def __init__(self):
        super().__init__()
        self._schema = None
        self._columns = DdlParseColumnDict()

    @property
    def is_temp(self):
        """Temporary Table Flag"""
        return self._is_temp

    @is_temp.setter
    def is_temp(self, flag):
        self._is_temp = flag

    @property
    def schema(self):
        """Schema name"""
        return self._schema

    @schema.setter
    def schema(self, schema):
        self._schema = schema

    @property
    def columns(self):
        """DdlParseColumn dictionary collection"""
        return self._columns

    def to_bigquery_fields(self, name_case=DdlParseBase.NAME_CASE.original):
        """Generate BigQuery JSON fields define"""

        bq_fields = []

        for col in self._columns.values():
            bq_fields.append(col.to_bigquery_field(name_case))

        return "[{}]".format(",".join(bq_fields))


class DdlParse(DdlParseBase):
    """DDL parser"""

    _LPAR, _RPAR, _COMMA, _SEMICOLON, _DOT, _DOUBLEQUOTE, _BACKQUOTE, _SPACE = map(Suppress, "(),;.\"` ")
    _CREATE, _TABLE, _TEMP, _CONSTRAINT, _NOT_NULL, _PRIMARY_KEY, _UNIQUE, _UNIQUE_KEY, _KEY = \
        map(CaselessKeyword, "CREATE, TABLE, TEMP, CONSTRAINT, NOT NULL, PRIMARY KEY, UNIQUE, UNIQUE KEY, KEY".replace(", ", ",").split(","))
    _SUPPRESS_QUOTE = _BACKQUOTE | _DOUBLEQUOTE

    _COMMENT = Suppress("--" + Regex(r".+"))

    _CREATE_TABLE_STATEMENT = Suppress(_CREATE) + Optional(_TEMP)("temp") + Suppress(_TABLE) + Optional(Suppress(CaselessKeyword("IF NOT EXISTS"))) \
        + Optional(_SUPPRESS_QUOTE) + Optional(Word(alphanums+"_")("schema") + Optional(_SUPPRESS_QUOTE) + _DOT + Optional(_SUPPRESS_QUOTE)) + Word(alphanums+"_<>")("table") + Optional(_SUPPRESS_QUOTE) \
        + _LPAR \
        + delimitedList(
            OneOrMore(
                # Ignore Index
                Suppress(_KEY + Word(alphanums+"_'`() "))
                |
                Group(
                    Optional(Suppress(_CONSTRAINT) + Word(alphanums+"_")("name"))
                    + (_PRIMARY_KEY ^ _UNIQUE ^ _UNIQUE_KEY ^ _NOT_NULL)("type")
                    + Optional(_SUPPRESS_QUOTE) + Optional(Word(alphanums+"_"))("name") + Optional(_SUPPRESS_QUOTE)
                    + _LPAR + Group(delimitedList(Optional(_SUPPRESS_QUOTE) + Word(alphanums+"_") + Optional(_SUPPRESS_QUOTE)))("constraint_columns") + _RPAR
                )("constraint")
                |
                Group(
                    Optional(_SUPPRESS_QUOTE) + Word(alphanums+"_")("name") + Optional(_SUPPRESS_QUOTE)
                    + Group(
                          Word(alphanums+"_")
                        + Optional(CaselessKeyword("WITHOUT TIME ZONE") ^ CaselessKeyword("WITH TIME ZONE") ^ CaselessKeyword("PRECISION"))
                        # + Optional(_LPAR + Word(nums+",") + _RPAR)
                        + Optional(_LPAR + Regex(r"\d+\s*,*\s*\d*") + _RPAR)
                        )("type")
                    + Optional(Word(alphanums+"_' "))("constraint")
                )("column")
            )
        )("columns")

    _DDL_PARSE_EXPR = Forward()
    _DDL_PARSE_EXPR << OneOrMore(_COMMENT | _CREATE_TABLE_STATEMENT)


    def __init__(self, ddl=None):
        super().__init__()
        self._ddl = ddl
        self._table = DdlParseTable()

    @property
    def ddl(self):
        """DDL script"""
        return self._ddl

    @ddl.setter
    def ddl(self, ddl):
        self._ddl = ddl

    def parse(self, ddl=None):
        """
        Parse DDL script.

        :param ddl: DDL script
        :return: DdlParseTable, Parsed table define info.
        """

        if ddl is not None:
            self._ddl = ddl

        if self._ddl is None:
            raise ValueError("DDL is not specified")

        ret = self._DDL_PARSE_EXPR.parseString(self._ddl)
        # print(ret.dump())

        if "schema" in ret:
            self._table.schema = ret["schema"]

        self._table.name = ret["table"]
        self._table.is_temp = True if "temp" in ret else False

        for ret_col in ret["columns"]:

            if ret_col.getName() == "column":
                # add column
                col = self._table.columns.append(ret_col["name"], ret_col["type"])

                if "constraint" in ret_col:
                    col.constraint = ret_col["constraint"]

            elif ret_col.getName() == "constraint":
                # set column constraint
                for col_name in ret_col["constraint_columns"]:
                    col = self._table.columns[col_name]

                    if ret_col["type"] == "PRIMARY KEY":
                        col.not_null = True
                        col.primary_key = True
                    elif ret_col["type"] in ["UNIQUE", "UNIQUE KEY"]:
                        col.unique = True
                    elif ret_col["type"] == "NOT NULL":
                        col.not_null = True

        return self._table