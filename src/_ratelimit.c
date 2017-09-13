#include <Python.h>
#include "structmember.h"

#include <time.h>
#include <sys/time.h>
#include <stdbool.h>

#ifdef __APPLE__
#include <mach/mach_time.h>
#endif

#define REBASE_TIME UINT32_MAX / 2

static uint64_t FAKE_NOW = 0;

#define C_ONLY

static PyObject *
get_fake_now(PyObject *cls, PyObject *args) {
    return PyLong_FromLong(FAKE_NOW);
}
static PyObject *
set_fake_now(PyObject *cls, PyObject *args) {
    if (! PyArg_ParseTuple(args, "K", &FAKE_NOW) )
        return NULL;

    Py_INCREF(Py_None);
    return Py_None;
}


typedef struct {
    PyObject_HEAD

    /* Type-specific fields go here. */
    uint64_t base;     // Base monotonic timestamp
    uint32_t current;  // Current element in *hits
    uint32_t csize;    // Currently allocated *hits size
    uint32_t bsize;    // By how much *hits will grow until it reaches max size
    uint32_t *hits;
} Rentry;

uint64_t naow() {
    // Used for unit tests
    if ( FAKE_NOW != 0 ) {
        return FAKE_NOW;
    }

#ifdef __APPLE__
    uint64_t absolute = mach_absolute_time() / (1000 * 1000);

    static mach_timebase_info_data_t sTimebaseInfo;
    if ( sTimebaseInfo.denom == 0 ) {
        mach_timebase_info(&sTimebaseInfo);
    }

    if ( sTimebaseInfo.numer == 1 && sTimebaseInfo.denom == 1) {
        return absolute;
    }

    return absolute * sTimebaseInfo.numer / sTimebaseInfo.denom;

#else
    struct timespec timecheck;

    clock_gettime(CLOCK_MONOTONIC, &timecheck);
    return (uint64_t)timecheck.tv_sec * 1000 + (uint64_t)timecheck.tv_nsec / (1000 * 1000);
#endif
}

static int
Rentry_init(Rentry *self, PyObject *args, PyObject *kwds)
{
    self->base = 0;
    self->current = 0;
    self->csize = 0;
    self->bsize = 10;
    self->hits = NULL;

    return 0;
}

static void
Rentry_dealloc(Rentry* self)
{
    free(self->hits);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyObject *
Rentry_hit(Rentry* self, uint32_t size, uint32_t delay) {
/*
    uint32_t size, delay;
    if (! PyArg_ParseTuple(args, "II", &size, &delay))
        return NULL;
*/
    uint64_t now = naow();

    if ( self->base == 0 ) {
        self->base = now - 1;
    }

    if ( self->current == self->csize ) {
        uint32_t i, new_size = (self->csize + self->bsize);
        //printf("realloc %d -> %d\n", self->csize, new_size);
        // XXX check NULL (realloc fail)
        self->hits = realloc(self->hits, new_size * sizeof(self->hits[0]));;
        // Unable to use memset properly
        //memset(self->hits + self->csize * sizeof(self->hits[0]), 0, self->bsize);
        for ( i = self->csize; i < new_size; i++ ) {
            self->hits[i] = 0;
        }
        
        self->csize = new_size;
    }

    if ( now - self->base > REBASE_TIME ) {
        //printf("rehash, now=%llu, base=%llu, dd=%llu, z==%d\n", now, pia->base, now-pia->base, z);
        uint32_t i;
        uint64_t min = 0;

        for ( i=0; i < self->csize; i ++) {
            if ( min != 0 && self->hits[i] != 0 && self->hits[i] < min ) {
                min = self->hits[i];
            }
        }

        uint64_t new_base = now - min - 1;
        uint32_t delta = (new_base - self->base);
        for ( i=0; i < self->csize; i++ ) {
            if ( self->hits[i] != 0 ) {
                self->hits[i] = delta + self->hits[i];
            }
        }
        self->base = new_base;
    }

    now -= self->base;

    uint64_t last = self->hits[self->current];
    //printf("Check, base=%llu, current=%u now=%llu, last=%llu ", self->base, self->current, now, last);
    //printf("Hit, now=%ld, last=%ld\n", now, last);

    if ( last != 0 && (now - last) < delay ) {
        Py_INCREF(Py_False);
        return Py_False;
    }

    self->hits[self->current] = now;
    if ( self->current == size - 1 ) {
        self->current = 0;
    } else {
        self->current++;
    }

    Py_INCREF(Py_True);
    return Py_True;
}

static PyMethodDef Rentry_methods[] = {
    {"hit", (PyCFunction)Rentry_hit, METH_VARARGS ,//| METH_KEYWORDS,
     "Hit me"
    },

    {NULL}  /* Sentinel */
};

static PyMemberDef Rentry_members[] = {
    {NULL}  /* Sentinel */
};


static PyTypeObject pyrated_RentryType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "pyrated._ratelimit.Rentry",  /* tp_name */
    sizeof(Rentry),               /* tp_basicsize */
    0,                            /* tp_itemsize */
    (destructor)Rentry_dealloc,   /* tp_dealloc */
    0,                            /* tp_print */
    0,                            /* tp_getattr */
    0,                            /* tp_setattr */
    0,                            /* tp_reserved */
    0,                            /* tp_repr */
    0,                            /* tp_as_number */
    0,                            /* tp_as_sequence */
    0,                            /* tp_as_mapping */
    0,                            /* tp_hash  */
    0,                            /* tp_call */
    0,                            /* tp_str */
    0,                            /* tp_getattro */
    0,                            /* tp_setattro */
    0,                            /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,           /* tp_flags */
    "pyrated Rentry objects",     /* tp_doc */
    0,                            /* tp_traverse */
    0,                            /* tp_clear */
    0,                            /* tp_richcompare */
    0,                            /* tp_weaklistoffset */
    0,                            /* tp_iter */
    0,                            /* tp_iternext */
    Rentry_methods,               /* tp_methods */
    Rentry_members,               /* tp_members */
    0,                            /* tp_getset */
    0,                            /* tp_base */
    0,                            /* tp_dict */
    0,                            /* tp_descr_get */
    0,                            /* tp_descr_set */
    0,                            /* tp_dictoffset */
    (initproc)Rentry_init,        /* tp_init */
    0,                            /* tp_alloc */
    PyType_GenericNew,            /* tp_new */
};


typedef struct {
    PyObject_HEAD

    /* Type-specific fields go here. */
    PyObject *entries;   // <dict> of str -> Rentry
    uint32_t count;     // how many hits per...
    uint32_t delay;    // how many milliseconds
} RatelimitBase;


static PyObject *
hhit(RatelimitBase *self, PyObject *args) {
    PyObject *key;

    if (! PyArg_ParseTuple(args, "O", &key) )
        return NULL;

    Rentry *value = (Rentry*) PyDict_GetItem(self->entries, key);

    if ( value == NULL ) {
        // Create new instance of Rentry
        value = (Rentry*) PyObject_CallObject((PyObject *) &pyrated_RentryType, NULL);

        PyDict_SetItem(self->entries, key,  (PyObject*) value);

        // Let the dict keep the ownership
        Py_DECREF(value);
    }

    PyObject *result = Rentry_hit(value, self->count, self->delay);
    return result;
}

static void
RatelimitBase_dealloc(RatelimitBase* self)
{
    //printf("dalloc list\n");
    Py_DECREF(self->entries);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static PyMethodDef pyrated_RatelimitBase_Methods[] = {
    {"hit",  (PyCFunction)hhit, METH_VARARGS,
     "hit test"},

    {NULL}        /* Sentinel */
};

static PyMemberDef pyrated_RatelimitBase_Members[] = {
    {"_entries", T_OBJECT_EX, offsetof(RatelimitBase, entries), 0,
     ""},
    {"_count", T_INT, offsetof(RatelimitBase, count), 0,
     ""},
    {"_delay", T_INT, offsetof(RatelimitBase, delay), 0,
     ""},
    {NULL}  /* Sentinel */
};


static PyTypeObject pyrated_RatelimiBaseType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "pyrated._ratelimit.RatelimitBase",  /* tp_name */
    sizeof(RatelimitBase),               /* tp_basicsize */
    0,                            /* tp_itemsize */
   (destructor)RatelimitBase_dealloc,   /* tp_dealloc */
    0,                            /* tp_print */
    0,                            /* tp_getattr */
    0,                            /* tp_setattr */
    0,                            /* tp_reserved */
    0,                            /* tp_repr */
    0,                            /* tp_as_number */
    0,                            /* tp_as_sequence */
    0,                            /* tp_as_mapping */
    0,                            /* tp_hash  */
    0,                            /* tp_call */
    0,                            /* tp_str */
    0,                            /* tp_getattro */
    0,                            /* tp_setattro */
    0,                            /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,           /* tp_flags */
    "Base type for RatelimitList",     /* tp_doc */
    0,                            /* tp_traverse */
    0,                            /* tp_clear */
    0,                            /* tp_richcompare */
    0,                            /* tp_weaklistoffset */
    0,                            /* tp_iter */
    0,                            /* tp_iternext */
    pyrated_RatelimitBase_Methods,               /* tp_methods */
    pyrated_RatelimitBase_Members,               /* tp_members */
    0,                            /* tp_getset */
    0,                            /* tp_base */
    0,                            /* tp_dict */
    0,                            /* tp_descr_get */
    0,                            /* tp_descr_set */
    0,                            /* tp_dictoffset */
    NULL,        /* tp_init */
    0,                            /* tp_alloc */
    PyType_GenericNew,                   /* tp_new */
};



static PyObject *
cleanup_dict(PyObject *cls, PyObject *args) {
    PyObject *dict;
    uint32_t delay;
    if (! PyArg_ParseTuple(args, "OI", &dict, &delay) )
        return NULL;
    
    PyObject *key, *value = NULL;
    Py_ssize_t pos = 0;

    const uint32_t BSIZE = 512; // Allocation block size for to_delete array
    uint32_t size = BSIZE;
    uint32_t count = 0;

    PyObject **to_delete = calloc(sizeof(PyObject*), size);

    const uint64_t now = naow();

    while (PyDict_Next(dict, &pos, &key, &value)) {
        Rentry *self = (Rentry*) value;

        if ( self->csize == 0 ) {
            // ADD

        } else {
            uint32_t index = 
                self->current == 0 ? self->csize - 1 : self->current - 1;
            uint64_t expires_at = self->base + self->hits[index] + delay;

            if ( expires_at <= now ) {
                // ADD
            } else {
                continue;
            }
        }

        // Bounds of array reached
        if ( count == size ) {
            size += BSIZE;
            to_delete = realloc(to_delete, size * sizeof(PyObject*));
        }
        to_delete[count++] = key;
        // printf("%zd, %s\n", pos, PyUnicode_AsUTF8(key));
    }

    for ( Py_ssize_t i = 0; i < count; i++) {
        PyDict_DelItem(dict, to_delete[i]);
    }

    free(to_delete);
    //Py_DECREF(dict);
    
    return PyLong_FromLong((long)count);
}

static PyMethodDef ModuleMethods[] = {
    {"_set_fake_now",  set_fake_now, METH_VARARGS,
     "Set the absolute time of fake internal clock "
     "to {value} milliseconds (for tests)"},
    {"_get_fake_now",  get_fake_now, METH_NOARGS,
     "Get the absolute time (in milliseconds of fake internal clock (for tests)"},
    {"cleanup_dict", cleanup_dict, METH_VARARGS, "Remove expired entries from dictionary"},
    {NULL}        /* Sentinel */
};

static PyModuleDef rentrymodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "pyrated._ratelimit",
    .m_doc = "C part of the ratelimit module.",
    .m_size = -1,
    .m_methods = ModuleMethods,
};

PyMODINIT_FUNC
PyInit__ratelimit(void)
{
    PyObject* module;

    //pyrated_RentryType.tp_new = PyType_GenericNew;
    if (PyType_Ready(&pyrated_RentryType) < 0)
        return NULL;

    //pyrated_RatelimiBaseType.tp_new = PyType_GenericNew;
    if (PyType_Ready(&pyrated_RatelimiBaseType) < 0)
        return NULL;

    module = PyModule_Create(&rentrymodule);
    if (module == NULL)
        return NULL;


    Py_INCREF(&pyrated_RentryType);
    Py_INCREF(&pyrated_RatelimiBaseType);
    PyModule_AddObject(module, "Rentry",(PyObject *)&pyrated_RentryType);
    PyModule_AddObject(module, "RatelimitBase", (PyObject *)&pyrated_RatelimiBaseType);

    return module;
}