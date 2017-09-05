

#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <sys/time.h>
#include <pthread.h>


#ifdef __APPLE__
#include <sys/types.h>
#include <sys/sysctl.h>
#include <mach/mach_init.h>
#include <mach/thread_act.h>
#include <mach/mach_time.h>
#else

#endif

// About 24 days
#define REHASH_TIME UINT32_MAX / 2


typedef struct Pia {
	uint64_t base;
	uint32_t current;
	uint32_t csize;
	uint32_t size;
	uint32_t bsize;
	uint32_t *hits;
} Pia;

pthread_t thread0;



uint64_t truenaow() {
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

static uint64_t NOW = 0;
uint64_t naow() {return truenaow();}


void *coucou() {

	NOW = naow();

	while (true) {
		NOW = truenaow();
		usleep(300);
	}

	return NULL;
}

Pia *init(int size, int bsize) {

	Pia *pia;
	//int msize = (sizeof(Pia) + (size * sizeof(pia->hits[0])));
	pia = malloc(sizeof(Pia));
	pia->size = size;
	pia->current = 0;
	pia->base = 0;
	pia->bsize = bsize;
	pia->csize = bsize;
	pia->hits = calloc(sizeof(pia->hits[0]), bsize);

	return pia;
}

void pia_debug(Pia *pia) {
	printf("pia %p, base=%llu, current=%u, hits=[", pia, pia->base, pia->current);
	int i;
	printf("%d", pia->hits[0]);
	for (i=1;i < pia->csize;i++) {
		printf(",%d", pia->hits[i]);
	}
	printf("]");
}

bool increment(Pia *pia) {
	uint64_t now = naow();

	if ( pia->base == 0 ) {
		pia->base = now - 1;
	}

	if ( pia->current == pia->csize ) {
		
		int i, new_size = (pia->csize + pia->bsize);
		//printf("realloc %d -> %d\n", pia->csize, new_size);
		// XXX check NULL (realloc fail)
		pia->hits = realloc(pia->hits, new_size * sizeof(pia->hits[0]));;
		// Unable to use memset properly
		//memset(pia->hits + pia->csize * sizeof(pia->hits[0]), 0, pia->bsize);
		for ( i = pia->csize; i < new_size; i++ ) {
			pia->hits[i] = 0;
		}
		
		pia->csize = new_size;
	}


	if ( now - pia->base > REHASH_TIME ) {
		uint32_t z = (uint32_t)-1 / 2;
		//printf("rehash, now=%llu, base=%llu, dd=%llu, z==%d\n", now, pia->base, now-pia->base, z);
		printf("rehash\n");
		pia_debug(pia);
		printf("\n");
		int i; uint64_t min = 0;
		//uint64_t *meh = calloc(uint64_t, pia->csize);

		for ( i=0; i < pia->csize; i ++) {
			if ( min != 0 && pia->hits[i] != 0 && pia->hits[i] < min ) {
				min = pia->hits[i];
			}
		}

		uint64_t new_base = now - min - 1;
		uint32_t delta = (new_base - pia->base);
		for ( i=0; i < pia->csize; i++ ) {
			if ( pia->hits[i] != 0 ) {
				pia->hits[i] = delta + pia->hits[i];
			}
		}
		pia->base = new_base;
	}

	now -= pia->base;

	uint64_t last = pia->hits[pia->current];
	//printf("Check, base=%llu, current=%u now=%llu, last=%llu ", pia->base, pia->current, now, last);
	//printf("Hit, now=%ld, last=%ld\n", now, last);

	if ( last != 0 && (now - last) < 2000 ) {
		//pia_debug(pia);
		return false;
	}

	pia->hits[pia->current] = now;
	if ( pia->current == pia->size - 1 ) {
		pia->current = 0;
	} else {
		pia->current++;
	}
	//pia_debug(pia);

	return true;
}

int main() {
	int i, j;
	uint64_t start, end;

	int OUTTER = 50000;
	int SIZE = 5;
	int INNER = 1000;

	struct timeval timecheck;

	//pthread_create(&thread0, NULL, coucou, NULL);
	
	start = truenaow();
	Pia *pia;
	if ( 1 ) {
		for (i = 0; i < OUTTER;i++) {
			pia = init(SIZE, 100);
			for (j=0;j < INNER; j++) {
				increment(pia);
			};
			
			free(pia->hits);
			free(pia);
		}
	} else if (0) {
		pia = init(5, 5);
		for (i =0 ; i<8;i++) {
			char r = increment(pia) ? 'y' : 'n';
			usleep(1000);
			
			printf("-> %c\n", r);
		
		}
		return 0;
	} else {
		pia = init(10, 10);
		while (true) {
			char c = getchar();
			if ( c != 10 ) break;

			char r = increment(pia) ? 'y' : 'n';
			printf("-> %c\n", r);
		}
	}

	end = truenaow();
	/*
	for (int i =0; i<SIZE; i++) {
		printf("%d: %ld\n", i, pia->hits[i]);
	}*/
	printf("%llu ms elapsed (%d op/s)\n", (end - start), ((OUTTER * INNER) / (end - start)  * 1000));

	sleep(10);

}
