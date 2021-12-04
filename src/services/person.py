from functools import lru_cache
from http import HTTPStatus
from typing import Optional

import orjson
from aioredis import Redis
from elasticsearch import AsyncElasticsearch
from fastapi import Depends, HTTPException

from services.utils import get_hits
from src.db.elastic import get_elastic
from src.db.redis import get_redis
from src.models.film import ESFilm, ListResponseFilm
from src.models.person import DetailResponsePerson, ElasticPerson
from src.services.mixins import ServiceMixin
from src.services.pagination import get_by_pagination


class PersonService(ServiceMixin):
    async def get_person(self, person_id: str):
        person = await self.get_by_id(target_id=person_id, schema=ElasticPerson)
        if not person:
            """Если персона не найдена, отдаём 404 статус"""
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="person not found"
            )
        return person

    async def get_person_films(
        self, film_ids: list[str], page: int, page_size: int
    ) -> Optional[dict]:
        body: dict = {
            "size": page_size,
            "from": (page - 1) * page_size,
            "query": {"ids": {"values": film_ids}},
        }
        key = str(str(page) + str(page_size) + 'persons' + str(body))
        instance = await self._get_result_from_cache(key=key)
        if not instance:

            docs: Optional[dict] = await self.search_in_elastic(body=body, _index="movies")

            hits = get_hits(docs, ESFilm)
            person_films: list[ListResponseFilm] = [
                ListResponseFilm(
                    uuid=film.id, title=film.title, imdb_rating=film.imdb_rating
                )
                for film in hits
            ]
            data = orjson.dumps([i.dict() for i in person_films])
            await self._put_data_to_cache(key=key, instance=data)

            return get_by_pagination(
                name="films",
                db_objects=person_films,
                total=len(hits),
                page=page,
                page_size=page_size,
            )
        person_films = [
            ListResponseFilm(**row) for row in orjson.loads(instance)
        ]

        return get_by_pagination(
            name="films",
            db_objects=person_films,
            total=len(person_films),
            page=page,
            page_size=page_size,
        )

    async def search_person(
        self, query: str, page: int, page_size: int
    ) -> Optional[dict]:
        body: dict = {
            "size": page_size,
            "from": (page - 1) * page_size,
            "query": {"bool": {"must": [{"match": {"full_name": query}}]}},
        }
        key = str(str(page) + str(page_size) + 'persons' + str(body))
        instance = await self._get_result_from_cache(key=key)

        if not instance:
            docs: Optional[dict] = await self.search_in_elastic(body=body)
            hits = get_hits(docs, ElasticPerson)
            persons: list[DetailResponsePerson] = [
                DetailResponsePerson(
                    uuid=es_person.id,
                    full_name=es_person.full_name,
                    role=es_person.roles[0],
                    film_ids=es_person.film_ids,
                )
                for es_person in hits
            ]

            data = orjson.dumps([i.dict() for i in persons])
            await self._put_data_to_cache(key=key, instance=data)

            return get_by_pagination(
                name="persons",
                db_objects=persons,
                total=len(hits),
                page=page,
                page_size=page_size,
            )
        persons = [
            DetailResponsePerson(**row) for row in orjson.loads(instance)
        ]

        return get_by_pagination(
            name="persons",
            db_objects=persons,
            total=len(persons),
            page=page,
            page_size=page_size,
        )


# get_person_service — это провайдер PersonService. Синглтон
@lru_cache()
def get_person_service(
    redis: Redis = Depends(get_redis),
    elastic: AsyncElasticsearch = Depends(get_elastic),
) -> PersonService:
    return PersonService(redis=redis, elastic=elastic, index="person")
