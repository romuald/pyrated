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

static PyObject *
pynaow(PyObject *cls, PyObject *args) {
    return PyLong_FromLong(naow());
}

static PyObject *
Rentry_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    Rentry *self;

    self = (Rentry *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->base = 0;
        self->current = 0;
        self->csize = 0;
        self->bsize = 0;
        self->hits = NULL;
    }

    return (PyObject *)self;
}

static int
Rentry_init(Rentry *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {"block_size", NULL};

     if (! PyArg_ParseTupleAndKeywords(args, kwds, "|I", kwlist, &self->bsize))
        return -1;

    if (self->bsize == 0) {
        self->bsize = 10; // XXX use ratio
    }

    return 0;
}

static void
Rentry_dealloc(Rentry* self)
{
    free(self->hits);
    Py_TYPE(self)->tp_free((PyObject*)self);
}


static PyObject *
Rentry_hit(Rentry* self, PyObject *args)
{
    uint32_t size, delay;
    if (! PyArg_ParseTuple(args, "II", &size, &delay))
        return NULL;

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

static PyObject *
Rentry_is_expired(Rentry* self, PyObject *args)
{
    uint64_t now;
    uint32_t delay;

    if (! PyArg_ParseTuple(args, "KI", &now, &delay))
        return NULL;

    PyObject *result;

    if ( self->csize == 0 ) {
        result = Py_True;
    } else {

        uint32_t index = 
            self->current == 0 ? self->csize - 1 : self->current - 1;
        uint64_t expires_at = self->base + self->hits[index] + delay;

        result = expires_at < now ? Py_True : Py_False;
        
        //printf("E? base=%llu, now=%llu, i=%d, previous=%d, expired=%c\n",
        //   self->base, now, index, self->hits[index], result == Py_True ? 'y': 'n');
    }

    Py_INCREF(result);

    return result;
}

static PyMethodDef Rentry_methods[] = {
    {"hit", (PyCFunction)Rentry_hit, METH_VARARGS ,//| METH_KEYWORDS,
     "Hit me"
    },
    {"is_expired", (PyCFunction)Rentry_is_expired, METH_VARARGS,
     "Is entry expired?"},

    {NULL}  /* Sentinel */
};

static PyMemberDef Rentry_members[] = {
    {"current", T_INT, offsetof(Rentry, current), 0,
     "noddy number"},
    /*{"zoub", T_INT, offsetof(Rentry, zoub), READONLY,
     "A zoub"},*/
    {NULL}  /* Sentinel */
};


static PyTypeObject pyrated_RentryType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "pyrated.rentry.Rentry",      /* tp_name */
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
    Rentry_new,                   /* tp_new */
};


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
     "Meh"},
    {"_get_fake_now",  get_fake_now, METH_NOARGS,
     "Meh"},
    {"now", (PyCFunction)pynaow, METH_NOARGS, "Monotonic now"},
    {"cleanup_dict", cleanup_dict, METH_VARARGS, "Mehmh"},
    {NULL}        /* Sentinel */
};

static PyModuleDef rentrymodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "pyrated.rentry",
    .m_doc = "Example module that creates an extension type.",
    .m_size = -1,
    .m_methods = ModuleMethods,
};

PyMODINIT_FUNC
PyInit_rentry(void)
{
    PyObject* m;

    pyrated_RentryType.tp_new = PyType_GenericNew;
    if (PyType_Ready(&pyrated_RentryType) < 0)
        return NULL;

    m = PyModule_Create(&rentrymodule);
    if (m == NULL)
        return NULL;


    Py_INCREF(&pyrated_RentryType);
    PyModule_AddObject(m, "Rentry", (PyObject *)&pyrated_RentryType);

    return m;
}