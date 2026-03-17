#ifndef PRINT_UTIL_H
#define PRINT_UTIL_H

#include <jansson.h>

int print_status(const char* response);
void print_type(json_t* element, int indent);
void print_indent(int indent);
void print_object(json_t *object, int indent);
void print_array(json_t *array, int indent);
void print_bool(json_t *element);

#endif
