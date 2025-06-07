from sqlalchemy.ext.asyncio import AsyncSession

from donna_common.orm.dal.collection import CollectionDAL
from donna_common.orm.dal.credit_transaction import CreditTransactionDAL
from donna_common.orm.dal.image import ImageDAL
from donna_common.orm.dal.mesh import MeshDAL
from donna_common.orm.dal.project import ProjectDAL
from donna_common.orm.dal.texture import TextureDAL
from donna_common.orm.dal.user import UserDAL


class MasterDAL:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.image_dal = ImageDAL(session)
        self.project_dal = ProjectDAL(session)
        self.mesh_dal = MeshDAL(session)
        self.user_dal = UserDAL(session)
        self.collection_dal = CollectionDAL(session)
        self.credit_transaction_dal = CreditTransactionDAL(session)
        self.texure_dal = TextureDAL(session)


async def get_master_dal(session: AsyncSession) -> MasterDAL:
    return MasterDAL(session)


# if __name__=="__main__":
#     asyncio.run(init_db())
