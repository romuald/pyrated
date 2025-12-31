#include <Python.h>
#include "structmember.h"

#include <time.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __APPLE__
#include <mach/mach_time.h>
#endif

// About 24 days
#define REBASE_TIME UINT32_MAX / 2

static uint64_t FAKE_NOW = 0;

static PyObject *
get_fake_now(PyObject *cls, PyObject *args) {
    return PyLong_FromLong(FAKE_NOW);
}

static PyObject *
set_fake_now(PyObject *cls, PyObject *args) {
    if (! PyArg_ParseTuple(args, "K", &FAKE_NOW) ) {
        return NULL;
    }

    Py_RETURN_NONE;
}

static uint64_t naow(void) {
    // Used for unit tests
    if ( FAKE_NOW != 0 ) {
        return FAKE_NOW;
    }

#ifdef __APPLE__
    uint64_t absolute = mach_absolute_time();

    static mach_timebase_info_data_t sTimebaseInfo;
    if ( sTimebaseInfo.denom == 0 ) {
        mach_timebase_info(&sTimebaseInfo);
    }

    uint64_t ns = (absolute * sTimebaseInfo.numer / sTimebaseInfo.denom);
    return ns / (1000 * 1000);
#elif defined(_WIN32)
    /* Warning (from documentation)

    The resolution of the GetTickCount64 function is limited to
    the resolution of the system timer, which is typically in
    the range of 10 milliseconds to 16 milliseconds
    */
    return (uint64_t)GetTickCount64();
#else
    struct timespec timecheck;

    clock_gettime(CLOCK_MONOTONIC, &timecheck);
    return (uint64_t)timecheck.tv_sec * 1000 + (uint64_t)timecheck.tv_nsec / (1000 * 1000);
#endif
}

typedef struct {
    PyObject_HEAD

    uint64_t base;     // Base monotonic timestamp
    uint32_t current;  // Current element in *hits
    uint32_t csize;    // Currently allocated *hits size
    uint32_t *hits;
} Rentry;

#if 0
static void reprint(PyObject *obj) {
    PyObject* repr = PyObject_Repr(obj);
    PyObject* str = PyUnicode_AsEncodedString(repr, "utf-8", "~E~");
    const char *bytes = PyBytes_AS_STRING(str);
    printf("REPR: %s\n", bytes);

    Py_XDECREF(repr);
    Py_XDECREF(str);
}

static void Rentry_debug(Rentry *self) {
    printf("Rentry %p, base=%llu, current=%u, hits=[", self, self->base, self->current);
    uint32_t i;
    printf("%d", self->hits[0]);
    for (i=1; i < self->csize; i++) {
        printf(",%d", self->hits[i]);
    }
    printf("]\n");
}
#endif

static int
Rentry_init(Rentry *self, PyObject *args, PyObject *kwds)
{
    self->base = 0;
    self->current = 0;
    self->csize = 0;
    self->hits = NULL;

    return 0;
}

static void
Rentry_dealloc(Rentry* self)
{
    PyMem_Free(self->hits);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

/*
    If this entry lived for more than X days, rewrite the internal references
    relative to now so they won't overflow
*/
static void
Rentry_rebase(Rentry* self, uint64_t now) {
    uint32_t i;
    uint64_t min = 0;

    for ( i=0; i < self->csize; i++ ) {
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

static inline void
Rentry_maybe_rebase(Rentry* self, uint64_t now) {
    if ( now - self->base < REBASE_TIME ) {
        return;
    }
    Rentry_rebase(self, now);
}

/*
    Records a hit for that entry at current time.
    Returning FALSE if the ratelimit was reached, and TRUE if it was not.
*/
static bool
Rentry_hit(Rentry* self, uint32_t size, uint32_t period, uint32_t bsize) {
    uint64_t now = naow();

    if ( self->base == 0 ) {
        self->base = now - 1;
    }

    if ( self->current == self->csize ) {
        uint32_t i;
        uint32_t new_size = (self->csize + bsize);
        if ( new_size > size ) {
            // Don't allocate more than necessary
            new_size = size;
        }

        //printf("realloc %d -> %d\n", self->csize, new_size);
        uint32_t* success = PyMem_Resize(self->hits, typeof(self->hits[0]), new_size);
        if (success == NULL) {
            return PyErr_NoMemory();
        }
        self->hits = success;

        /*
        // Unable to use memset properly
        memset(self->hits + self->csize * sizeof(self->hits[0]),
               0, (new_size - self->csize) * sizeof(self->hits[0]));
        */
        for ( i = self->csize; i < new_size; i++ ) {
            self->hits[i] = 0;
        }

        self->csize = new_size;
    }

    Rentry_maybe_rebase(self, now);

    now -= self->base;

    uint64_t last = self->hits[self->current];
    //printf("Check, base=%llu, current=%u now=%llu, last=%llu ",
    //       self->base, self->current, now, last);
    //printf("Hit, now=%ld, last=%ld\n", now, last);

    if ( last != 0 && (now - last) < period ) {
        return false;
    }

    self->hits[self->current] = now;
    if ( self->current == size - 1 ) {
        self->current = 0;
    } else {
        self->current++;
    }

    return true;
}

/*
    Returns the interval (in milliseconds) after which a rateilmited entry
    will be available again
*/
static uint64_t
Rentry_next_hit(Rentry* self, uint32_t size, uint32_t period) {
    if ( self->csize < size ) {
        return 0;
    }

    uint64_t now = naow();
    Rentry_maybe_rebase(self, now);

    now -= self->base;

    uint64_t last = self->hits[self->current];

    if ( last != 0 && (now - last) < period ) {
        return last + period - now;
    }
    return 0;
}

#define STATE_VERSION 0
#define STATE_BASE 1
#define STATE_CURRENT 2
#define STATE_CSIZE 3
#define STATE_HITS 4

/* Retrieve state for serialization */
static PyObject *
Rentry_get_state(Rentry* self) {
    PyObject *state, *tmp;
    state  = PyTuple_New(5);

    PyTuple_SetItem(state, STATE_VERSION,
        PyLong_FromUnsignedLong(1));
    PyTuple_SetItem(state, STATE_BASE,
        PyLong_FromUnsignedLong(self->base));
    PyTuple_SetItem(state, STATE_CURRENT,
        PyLong_FromUnsignedLong(self->current));
    PyTuple_SetItem(state, STATE_CSIZE,
        PyLong_FromUnsignedLong(self->csize));

    tmp = PyBytes_FromStringAndSize((char*)self->hits, self->csize);
    PyTuple_SetItem(state, STATE_HITS, tmp);

    return state;
}

/* Re-set state from the get_state serialization */
static PyObject *
Rentry_set_state(Rentry* self, PyObject *args) {
    PyObject *state;
    if (! PyArg_ParseTuple(args, "O", &state) ) {
        return NULL;
    }

    self->base = PyLong_AsLong(PyTuple_GetItem(state, STATE_BASE));
    self->current = PyLong_AsLong(PyTuple_GetItem(state, STATE_CURRENT));
    self->csize = PyLong_AsLong(PyTuple_GetItem(state, STATE_CSIZE));

    self->hits = PyMem_Calloc(self->csize, sizeof(self->hits[0]));
    if (self->hits == NULL) {
        return PyErr_NoMemory();;
    }
    char *hits = PyBytes_AsString(PyTuple_GetItem(state, STATE_HITS));
    memcpy(self->hits, hits, self->csize);

    Py_RETURN_NONE;
}

static PyMethodDef pyrated_Rentry_Methods[] = {
    {"__getstate__", (PyCFunction)Rentry_get_state, METH_NOARGS,
     "Serialize function"},
     {"__setstate__", (PyCFunction)Rentry_set_state, METH_VARARGS,
     "Deserialize function"},

      {NULL}        /* Sentinel */
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
    pyrated_Rentry_Methods,       /* tp_methods */
    0,                            /* tp_members */
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

    PyObject *entries;   // <dict> of str -> Rentry
    uint32_t count;     // how many hits per...
    uint32_t period;    // how many milliseconds
    uint32_t block_size; // By how much entry->*hits will grow until it reaches max size
} RatelimitBase;


/*
    Hit an entry in the table, creating it if need be
*/
static PyObject *
RatelimitBase_hit(RatelimitBase *self, PyObject *args) {
    PyObject *key, *result;

    if (! PyArg_ParseTuple(args, "O", &key) ) {
        return NULL;
    }

    Rentry *value = (Rentry*) PyDict_GetItem(self->entries, key);

    if ( value == NULL ) {
        // Create new instance of Rentry
        value = (Rentry*) PyObject_CallObject((PyObject *) &pyrated_RentryType, NULL);

        PyDict_SetItem(self->entries, key,  (PyObject*) value);

        // Let the dict keep the ownership
        Py_DECREF(value);
    }

    if (Rentry_hit(value, self->count, self->period, self->block_size)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

/*
    Table version of the Rentry_next_hit call (do not create new entries)
*/
static PyObject *
RatelimitBase_next_hit(RatelimitBase *self, PyObject *args) {
    PyObject *key;

    if (! PyArg_ParseTuple(args, "O", &key) ) {
        return NULL;
    }

    Rentry *value = (Rentry*) PyDict_GetItem(self->entries, key);

    if ( value == NULL ) {
        return PyLong_FromUnsignedLong(0);
    }

    uint64_t result = Rentry_next_hit(value, self->count, self->period);

    return PyLong_FromUnsignedLong(result);
}

/*
    Cleanup entries in the table that have expired
    (no hit since the total period)
*/
static PyObject *
RatelimitBase_cleanup(RatelimitBase *self, PyObject *args) {
    PyObject *key, *value = NULL;
    Py_ssize_t pos = 0;

    const uint32_t BSIZE = 512; // Allocation block size for to_delete array
    uint32_t size = BSIZE;
    uint32_t count = 0;

    PyObject **to_delete = PyMem_Calloc(sizeof(PyObject*), size);

    if (to_delete == NULL) {
        return PyErr_NoMemory();
    }

    const uint64_t now = naow();

    while (PyDict_Next(self->entries, &pos, &key, &value)) {
        Rentry *entry = (Rentry*) value;

        if ( entry->csize == 0 ) {
            // Remove entry
        } else {
            uint32_t index =
                entry->current == 0 ? entry->csize - 1 : entry->current - 1;
            uint64_t expires_at = entry->base + entry->hits[index] + self->period;

            if ( expires_at <= now ) {
                // Remove entry
            } else {
                // SKIP
                continue;
            }
        }

        // Bounds of array reached
        if ( count == size ) {
            size += BSIZE;
            // XXX check for failed call
            to_delete = realloc(to_delete, size * sizeof(PyObject*));
        }
        to_delete[count++] = key;
    }

    uint32_t i;
    for ( i = 0; i < count; i++ ) {
        PyDict_DelItem(self->entries, to_delete[i]);
    }
    PyMem_Free(to_delete);

    return PyLong_FromLong((long)count);
}


static void
RatelimitBase_dealloc(RatelimitBase* self)
{
    Py_XDECREF(self->entries);
    Py_TYPE(self)->tp_free((PyObject*)self);
}

static int
RatelimitBase_traverse(RatelimitBase *self, visitproc visit, void *arg)
{
    Py_VISIT(self->entries);

    return 0;
}

static int
RatelimitBase_clear(RatelimitBase *self)
{
    Py_CLEAR(self->entries);

    return 0;
}

static PyMethodDef pyrated_RatelimitBase_Methods[] = {
    {"hit",  (PyCFunction)RatelimitBase_hit, METH_VARARGS,
     "\"hit\" the ratelimit for a specific key, will return True if rate is "
     "within the current limits specifications for that key"},
    {"next_hit",  (PyCFunction)RatelimitBase_next_hit, METH_VARARGS,
     "For how many milliseconds hit() will reply with False"},
    {"cleanup", (PyCFunction)RatelimitBase_cleanup, METH_NOARGS,
     "Remove expired entries from the list"},

    {NULL}        /* Sentinel */
};

static PyMemberDef pyrated_RatelimitBase_Members[] = {
    {"_entries", T_OBJECT_EX, offsetof(RatelimitBase, entries), 0,
     "Dict of key->Rentry"},
    {"_count", T_INT, offsetof(RatelimitBase, count), 0,
     "How much hits are allowed"},
    {"_period", T_INT, offsetof(RatelimitBase, period), 0,
     "The period (in milliseconds) over which the hits are allowed"},
    {"_block_size", T_INT, offsetof(RatelimitBase, block_size), 0,
     "Allocation block size"},
    {NULL}  /* Sentinel */
};


static PyTypeObject pyrated_RatelimitBaseType = {
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
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,    /* tp_flags */
    "Base type for RatelimitList",               /* tp_doc */
    RatelimitBase_traverse,       /* tp_traverse */
    RatelimitBase_clear,          /* tp_clear */
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
    NULL,                         /* tp_init */
    0,                            /* tp_alloc */
    PyType_GenericNew,            /* tp_new */
};

static PyMethodDef ModuleMethods[] = {
    {"_set_fake_now",  set_fake_now, METH_VARARGS,
     "Set the absolute time of fake internal clock "
     "to {value} milliseconds (for tests)"},
    {"_get_fake_now",  get_fake_now, METH_NOARGS,
     "Get the absolute time (in milliseconds of fake internal clock (for tests)"},
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

    if (PyType_Ready(&pyrated_RentryType) < 0) {
        return NULL;
    }

    if (PyType_Ready(&pyrated_RatelimitBaseType) < 0) {
        return NULL;
    }

    module = PyModule_Create(&rentrymodule);
    if (module == NULL) {
        return NULL;
    }


    Py_INCREF(&pyrated_RentryType);
    Py_INCREF(&pyrated_RatelimitBaseType);
    PyModule_AddObject(module, "Rentry",(PyObject *)&pyrated_RentryType);
    PyModule_AddObject(module, "RatelimitBase", (PyObject *)&pyrated_RatelimitBaseType);

    return module;
}
